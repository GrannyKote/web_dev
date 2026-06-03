"""Kafka-консьюмер для order_service.

Получает команды (list / update / delete) из топика `order.commands`,
исполняет их и публикует ответ в reply_topic (обычно `admin.replies`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .database import SessionLocal

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
COMMANDS_TOPIC = os.getenv("ORDER_COMMANDS_TOPIC", "order.commands")
CONSUMER_GROUP = os.getenv("ORDER_CONSUMER_GROUP", "order-service")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://127.0.0.1:8000")


def _to_order_dict(order: models.Order) -> dict[str, Any]:
    return schemas.OrderResponse(
        id=order.id,
        number=order.number,
        delivery=order.delivery,
        address=order.address,
        phone=order.phone,
        status=order.status,
        amount=order.amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
        items=order.items,
    ).model_dump(mode="json")


def _ok(status_code: int, body: Any) -> dict[str, Any]:
    return {"status_code": status_code, "body": body, "error": None}


def _err(status_code: int, message: str) -> dict[str, Any]:
    return {"status_code": status_code, "body": None, "error": message}


async def _fetch_catalog_item(item_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Возвращает (item, error). Один из них — None."""
    url = f"{CATALOG_SERVICE_URL}/catalog/{item_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return None, _err(502, f"Catalog service unavailable: {exc}")

    if response.status_code == 404:
        return None, _err(400, f"Item {item_id} not found in catalog")
    if response.status_code >= 400:
        return None, _err(502, f"Catalog service returned status {response.status_code}")
    return response.json(), None


def _handle_list(db: Session) -> dict[str, Any]:
    orders = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .order_by(models.Order.id.desc())
        .all()
    )
    return _ok(200, [_to_order_dict(order) for order in orders])


async def _handle_update(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    order_id = payload.get("order_id")
    data = payload.get("data") or {}
    if not isinstance(order_id, int):
        return _err(400, "order_id is required")
    order = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(models.Order.id == order_id)
        .first()
    )
    if order is None:
        return _err(404, "Order not found")
    try:
        update = schemas.OrderUpdate(**data)
    except ValidationError as exc:
        return _err(422, exc.json())

    if update.delivery is not None:
        order.delivery = update.delivery
    if update.address is not None:
        order.address = update.address
    if update.phone is not None:
        order.phone = update.phone
    if update.status is not None:
        order.status = update.status

    if update.items is not None:
        db.query(models.OrderItem).filter(models.OrderItem.id_order == order.id).delete()
        total = 0.0
        for entry in update.items:
            item, error = await _fetch_catalog_item(entry.item_id)
            if error is not None:
                db.rollback()
                return error
            assert item is not None
            price = float(item.get("price", 0))
            quantity = entry.quantity
            total += price * quantity
            db.add(
                models.OrderItem(
                    id_order=order.id,
                    id_item=entry.item_id,
                    name=item.get("name", "Unknown item"),
                    quantity=quantity,
                    price=price,
                )
            )
        order.amount = round(total, 2)

    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    refreshed = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(models.Order.id == order.id)
        .first()
    )
    return _ok(200, _to_order_dict(refreshed))


def _handle_delete(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    order_id = payload.get("order_id")
    if not isinstance(order_id, int):
        return _err(400, "order_id is required")
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        return _err(404, "Order not found")
    db.delete(order)
    db.commit()
    return _ok(204, None)


async def _process(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    db = SessionLocal()
    try:
        if operation == "list":
            return _handle_list(db)
        if operation == "update":
            return await _handle_update(db, payload)
        if operation == "delete":
            return _handle_delete(db, payload)
        return _err(400, f"Unknown operation: {operation}")
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Order command failed: %s", operation)
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
        "Order Kafka consumer started: bootstrap=%s topic=%s group=%s",
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
                        logger.warning("Invalid JSON in order command, skipping")
                        continue

                    correlation_id = envelope.get("correlation_id")
                    reply_topic = envelope.get("reply_topic")
                    operation = envelope.get("operation", "")
                    payload = envelope.get("payload") or {}

                    result = await _process(operation, payload)

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
        logger.info("Order Kafka consumer stopped")


__all__ = ["run_consumer"]
