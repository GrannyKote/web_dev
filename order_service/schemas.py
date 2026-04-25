from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_STATUSES = [
    "Создан",
    "Передан в доставку",
    "Доставлен/Готов к выдаче",
    "Оплачен",
    "Отменен",
    "delivered",
]


class OrderItemCreate(BaseModel):
    item_id: int
    quantity: int = Field(default=1, ge=1)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    id_order: int
    id_item: int
    name: str
    quantity: int | None = None
    price: float | None = None


class OrderCreate(BaseModel):
    delivery: bool
    address: str | None = None
    phone: str
    items: list[OrderItemCreate]

    @model_validator(mode="after")
    def validate_delivery_address(self) -> "OrderCreate":
        if self.delivery and not self.address:
            raise ValueError("Address is required when delivery is true")
        return self


class OrderUpdate(BaseModel):
    delivery: bool | None = None
    address: str | None = None
    phone: str | None = None
    status: str | None = None
    items: list[OrderItemCreate] | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "OrderUpdate":
        if self.status is not None and self.status not in ALLOWED_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(ALLOWED_STATUSES)}")
        return self


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    delivery: bool
    address: str | None = None
    phone: str
    status: str | None = None
    amount: float | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
