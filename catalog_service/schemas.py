from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str | None = None
    description: str | None = ""
    feature_1: str | None = None
    feature_2: float | None = None
    feature_3: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    photo: str | None = None
    price: float | None = 0
    stock: int | None = 0


class ItemCreate(ItemBase):
    name: str


class ItemUpdate(ItemBase):
    pass


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    feature_1: str | None = None
    feature_2: float | None = None
    feature_3: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    photo: str | None = None
    price: float
    stock: int
