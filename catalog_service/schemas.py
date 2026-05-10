from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import FEATURE_1_ALLOWED

Feature1Value = Literal["вариант 1", "вариант 2"]


class ItemBase(BaseModel):
    name: str | None = None
    description: str | None = ""
    feature_1: Feature1Value | None = None
    feature_2: float | None = None
    feature_3: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    photo: str | None = None
    price: float | None = 0
    stock: int | None = 0

    @field_validator("feature_1", mode="before")
    @classmethod
    def normalize_feature_1(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if value not in FEATURE_1_ALLOWED:
            allowed = ", ".join(sorted(FEATURE_1_ALLOWED))
            raise ValueError(f"feature_1 must be one of: {allowed}")
        return value


class ItemCreate(ItemBase):
    name: str


class ItemUpdate(ItemBase):
    pass


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    feature_1: Feature1Value | None = None
    feature_2: float | None = None
    feature_3: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    photo: str | None = None
    price: float
    stock: int
