"""Kafka RPC-клиент: отправляет команды и ждёт ответ по correlation_id.

Используется в admin_service для запросов к catalog_service и order_service.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
ADMIN_REPLY_TOPIC = os.getenv("ADMIN_REPLY_TOPIC", "admin.replies")
ADMIN_CONSUMER_GROUP = os.getenv("ADMIN_CONSUMER_GROUP", "admin-service")
DEFAULT_REQUEST_TIMEOUT = float(os.getenv("ADMIN_KAFKA_TIMEOUT", "15"))

CATALOG_COMMANDS_TOPIC = os.getenv("CATALOG_COMMANDS_TOPIC", "catalog.commands")
ORDER_COMMANDS_TOPIC = os.getenv("ORDER_COMMANDS_TOPIC", "order.commands")


class KafkaUnavailable(RuntimeError):
    """Не удалось подключиться/обратиться к Kafka."""


class KafkaRPCClient:
    """Производитель команд и потребитель ответов (request-reply поверх Kafka).

    Каждое сообщение-команда содержит correlation_id и reply_topic.
    Сервисы-получатели обрабатывают команду и публикуют ответ в reply_topic.
    Этот клиент сопоставляет ответы с ожидающими futures по correlation_id.
    """

    def __init__(
        self,
        *,
        reply_topic: str = ADMIN_REPLY_TOPIC,
        group_id: str = ADMIN_CONSUMER_GROUP,
        bootstrap_servers: str = KAFKA_BOOTSTRAP,
    ) -> None:
        self.reply_topic = reply_topic
        self.group_id = group_id
        self.bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._consume_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        if self._started:
            return
        self._producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self._producer.start()
        # Уникальная подписка на ответы для каждого экземпляра клиента,
        # чтобы все ответы доходили до того, кто отправил запрос.
        consumer_group = f"{self.group_id}-{uuid.uuid4()}"
        self._consumer = AIOKafkaConsumer(
            self.reply_topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=consumer_group,
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._consume_task = asyncio.create_task(self._consume_replies())
        self._started = True
        logger.info(
            "Kafka RPC client started: bootstrap=%s reply_topic=%s",
            self.bootstrap_servers,
            self.reply_topic,
        )

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._consume_task is not None:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
            self._consume_task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(KafkaUnavailable("Kafka client stopped"))
        self._pending.clear()

    async def _consume_replies(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                try:
                    data = json.loads(msg.value.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning("Invalid reply payload, skipping")
                    continue
                cid = data.get("correlation_id")
                if not isinstance(cid, str):
                    continue
                fut = self._pending.pop(cid, None)
                if fut is not None and not fut.done():
                    fut.set_result(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reply consumer loop crashed")

    async def request(
        self,
        topic: str,
        operation: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
    ) -> dict[str, Any]:
        if not self._started or self._producer is None:
            raise KafkaUnavailable("Kafka RPC client is not started")
        correlation_id = str(uuid.uuid4())
        envelope = {
            "correlation_id": correlation_id,
            "reply_topic": self.reply_topic,
            "operation": operation,
            "payload": payload or {},
        }
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[correlation_id] = future
        try:
            await self._producer.send_and_wait(
                topic, json.dumps(envelope, ensure_ascii=False).encode("utf-8")
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(correlation_id, None)
            raise KafkaUnavailable(
                f"Kafka RPC timeout after {timeout}s for {topic}/{operation}"
            ) from exc
        except Exception:
            self._pending.pop(correlation_id, None)
            raise


__all__ = [
    "KafkaRPCClient",
    "KafkaUnavailable",
    "CATALOG_COMMANDS_TOPIC",
    "ORDER_COMMANDS_TOPIC",
]
