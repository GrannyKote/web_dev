"""Сервис администрирования каталога и заказов.

Эндпоинты:
- POST   /admin/catalog          — создать товар (требует JWT)
- PUT    /admin/catalog/{id}     — обновить товар (требует JWT)
- DELETE /admin/catalog/{id}     — удалить товар (требует JWT)
- GET    /admin/order            — список заказов (требует JWT)
- PUT    /admin/order/{id}       — обновить заказ (требует JWT)
- DELETE /admin/order/{id}       — удалить заказ (требует JWT)

Все операции выполняются через Kafka — admin_service не обращается к
catalog_service / order_service по HTTP, а отправляет команды в kafka-топики
и ждёт ответа в `admin.replies`.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import CurrentUser, require_auth
from .kafka_client import (
    CATALOG_COMMANDS_TOPIC,
    ORDER_COMMANDS_TOPIC,
    KafkaRPCClient,
    KafkaUnavailable,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Admin Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    client = KafkaRPCClient()
    try:
        await client.start()
    except Exception:
        logger.exception("Failed to start Kafka RPC client")
        # сервис должен подняться, даже если Kafka недоступна;
        # запросы будут возвращать 503, пока Kafka не появится.
    app.state.kafka_client = client


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client: KafkaRPCClient | None = getattr(app.state, "kafka_client", None)
    if client is not None:
        await client.stop()


def _kafka_client(request: Request) -> KafkaRPCClient:
    client: KafkaRPCClient | None = getattr(request.app.state, "kafka_client", None)
    if client is None or not client.started:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka недоступен, попробуйте позже",
        )
    return client


def _to_http_response(result: dict[str, Any]) -> Response:
    status_code = int(result.get("status_code") or 500)
    error = result.get("error")
    body = result.get("body")
    if status_code >= 400:
        detail = error or (body if isinstance(body, str) else "Ошибка обработки команды")
        raise HTTPException(status_code=status_code, detail=detail)
    if status_code == status.HTTP_204_NO_CONTENT or body is None:
        return Response(status_code=status_code)
    return Response(
        content=json.dumps(body, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


async def _send_command(
    request: Request, topic: str, operation: str, payload: dict[str, Any] | None = None
) -> Response:
    client = _kafka_client(request)
    try:
        result = await client.request(topic, operation, payload)
    except KafkaUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kafka недоступна: {exc}",
        ) from exc
    return _to_http_response(result)


@app.get("/admin/health")
async def health(request: Request) -> dict[str, Any]:
    client: KafkaRPCClient | None = getattr(request.app.state, "kafka_client", None)
    return {
        "status": "ok",
        "kafka_connected": bool(client and client.started),
    }


# ---------- Catalog admin ----------


@app.post("/admin/catalog", status_code=status.HTTP_201_CREATED)
async def create_catalog_item(
    request: Request,
    payload: dict[str, Any],
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(request, CATALOG_COMMANDS_TOPIC, "create", payload)


@app.put("/admin/catalog/{item_id}")
async def update_catalog_item(
    item_id: int,
    request: Request,
    payload: dict[str, Any],
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(
        request,
        CATALOG_COMMANDS_TOPIC,
        "update",
        {"item_id": item_id, "data": payload},
    )


@app.delete("/admin/catalog/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_item(
    item_id: int,
    request: Request,
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(
        request, CATALOG_COMMANDS_TOPIC, "delete", {"item_id": item_id}
    )


# ---------- Order admin ----------


@app.get("/admin/order")
async def list_orders(
    request: Request,
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(request, ORDER_COMMANDS_TOPIC, "list")


@app.put("/admin/order/{order_id}")
async def update_order(
    order_id: int,
    request: Request,
    payload: dict[str, Any],
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(
        request,
        ORDER_COMMANDS_TOPIC,
        "update",
        {"order_id": order_id, "data": payload},
    )


@app.delete("/admin/order/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: int,
    request: Request,
    _: CurrentUser = Depends(require_auth),
) -> Response:
    return await _send_command(
        request, ORDER_COMMANDS_TOPIC, "delete", {"order_id": order_id}
    )
