import os
from collections.abc import Generator
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from . import models, schemas
from .database import SessionLocal, init_db

app = FastAPI(title="Order Service")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://127.0.0.1:8000")

init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def fetch_catalog_item(item_id: int) -> dict:
    url = f"{CATALOG_SERVICE_URL}/catalog/{item_id}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Catalog service unavailable: {exc}",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item {item_id} not found in catalog",
        )
    if response.status_code >= status.HTTP_400_BAD_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Catalog service returned status {response.status_code}",
        )
    return response.json()


def to_order_response(order: models.Order) -> schemas.OrderResponse:
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
    )


@app.get("/order/{number}", response_model=schemas.OrderResponse)
def get_order_by_number(number: str, db: Session = Depends(get_db)) -> schemas.OrderResponse:
    order = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(models.Order.number == number)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return to_order_response(order)


@app.post("/order", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
async def add_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)) -> schemas.OrderResponse:
    order = models.Order(
        number="TEMP",
        delivery=payload.delivery,
        address=payload.address,
        phone=payload.phone,
        status="Создан",
        amount=0,
    )
    db.add(order)
    db.flush()

    total = 0.0
    for entry in payload.items:
        item = await fetch_catalog_item(entry.item_id)
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

    order.number = f"ORD-{order.id:06d}"
    order.amount = round(total, 2)
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)
    order = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(models.Order.id == order.id)
        .first()
    )
    return to_order_response(order)


@app.put("/order/{order_id}", response_model=schemas.OrderResponse)
async def update_order(
    order_id: int,
    payload: schemas.OrderUpdate,
    db: Session = Depends(get_db),
) -> schemas.OrderResponse:
    order = (
        db.query(models.Order)
        .options(joinedload(models.Order.items))
        .filter(models.Order.id == order_id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if payload.delivery is not None:
        order.delivery = payload.delivery
    if payload.address is not None:
        order.address = payload.address
    if payload.phone is not None:
        order.phone = payload.phone
    if payload.status is not None:
        order.status = payload.status

    if payload.items is not None:
        db.query(models.OrderItem).filter(models.OrderItem.id_order == order.id).delete()
        total = 0.0
        for entry in payload.items:
            item = await fetch_catalog_item(entry.item_id)
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
    return to_order_response(refreshed)


@app.delete("/order/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(order_id: int, db: Session = Depends(get_db)) -> None:
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    db.delete(order)
    db.commit()
