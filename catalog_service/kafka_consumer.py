"""Kafka-консьюмер для catalog_service.

Получает команды (create / update / delete) из топика `catalog.commands`,
исполняет их через ORM и публикует ответ в reply_topic (обычно `admin.replies`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
import base64

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
COMMANDS_TOPIC = os.getenv("CATALOG_COMMANDS_TOPIC", "catalog.commands")
CONSUMER_GROUP = os.getenv("CATALOG_CONSUMER_GROUP", "catalog-service")


def _decode_photo(photo: str | None) -> bytes | None:
    if not photo:
        return None

    try:
        return base64.b64decode(photo, validate=True)
    except Exception:
        return photo.encode("utf-8")


def _encode_photo(photo: bytes | None) -> str | None:
    if photo is None:
        return None

    return base64.b64encode(photo).decode("utf-8")


def _to_response_dict(item: models.Item) -> dict[str, Any]:
    return schemas.ItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        feature_1=item.feature_1,
        feature_2=item.feature_2,
        feature_3=item.feature_3,
        features=item.features or {},
        photo=_encode_photo(item.photo),
        price=item.price,
        stock=item.stock,
    ).model_dump(mode="json")


def _ok(status_code: int, body: Any) -> dict[str, Any]:
    return {"status_code": status_code, "body": body, "error": None}


def _err(status_code: int, message: str) -> dict[str, Any]:
    return {"status_code": status_code, "body": None, "error": message}


def _handle_create(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        data = schemas.ItemCreate(**payload)
    except ValidationError as exc:
        return _err(422, exc.json())
    item = models.Item(
        name=data.name,
        description=data.description or "",
        feature_1=data.feature_1,
        feature_2=data.feature_2,
        feature_3=data.feature_3,
        features=data.features or {},
        photo=_decode_photo(data.photo),
        price=data.price if data.price is not None else 0,
        stock=data.stock if data.stock is not None else 0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _ok(201, _to_response_dict(item))


def _handle_update(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    item_id = payload.get("item_id")
    update_payload = payload.get("data") or {}
    if not isinstance(item_id, int):
        return _err(400, "item_id is required")
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if item is None:
        return _err(404, "Item not found")
    try:
        update_values = schemas.ItemUpdate(**update_payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        return _err(422, exc.json())
    if "photo" in update_values:
        item.photo = _decode_photo(update_values.pop("photo"))
    for key, value in update_values.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _ok(200, _to_response_dict(item))


def _handle_delete(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    item_id = payload.get("item_id")
    if not isinstance(item_id, int):
        return _err(400, "item_id is required")
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if item is None:
        return _err(404, "Item not found")
    db.delete(item)
    db.commit()
    return _ok(204, None)


def _process(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    db = SessionLocal()
    try:
        if operation == "create":
            return _handle_create(db, payload)
        if operation == "update":
            return _handle_update(db, payload)
        if operation == "delete":
            return _handle_delete(db, payload)
        return _err(400, f"Unknown operation: {operation}")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Catalog command failed: %s", operation)
        return _err(500, f"Internal error: {exc}")
    finally:
        db.close()


async def run_consumer(stop_event: asyncio.Event) -> None:
    consumer = AIOKafkaConsumer(
        COMMANDS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=CONSUMER_GROUP,
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await consumer.start()
    await producer.start()
    logger.info(
        "Catalog Kafka consumer started: bootstrap=%s topic=%s group=%s",
        KAFKA_BOOTSTRAP,
        COMMANDS_TOPIC,
        CONSUMER_GROUP,
    )
    try:
        while not stop_event.is_set():
            batch = await consumer.getmany(timeout_ms=1000)
            for _tp, messages in batch.items():
                for msg in messages:
                    try:
                        envelope = json.loads(msg.value.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        logger.warning("Invalid JSON in catalog command, skipping")
                        continue

                    correlation_id = envelope.get("correlation_id")
                    reply_topic = envelope.get("reply_topic")
                    operation = envelope.get("operation", "")
                    payload = envelope.get("payload") or {}

                    result = await asyncio.get_running_loop().run_in_executor(
                        None, _process, operation, payload
                    )

                    if correlation_id and reply_topic:
                        reply = {"correlation_id": correlation_id, **result}
                        try:
                            await producer.send_and_wait(
                                reply_topic,
                                json.dumps(reply, ensure_ascii=False).encode("utf-8"),
                            )
                        except Exception:
                            logger.exception(
                                "Failed to publish reply for %s", correlation_id
                            )
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("Catalog Kafka consumer stopped")


__all__ = ["run_consumer"]
