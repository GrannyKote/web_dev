from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base, DB_SCHEMA


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "order"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(64), nullable=False, unique=True, index=True)
    delivery = Column(Boolean, nullable=False)
    address = Column(String(512), nullable=True)
    phone = Column(String(64), nullable=False)
    status = Column(String(64), nullable=True)
    amount = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_item"

    id = Column(Integer, primary_key=True, index=True)
    id_order = Column(
        Integer,
        ForeignKey(f"{DB_SCHEMA}.order.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    id_item = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=True)
    price = Column(Float, nullable=True)

    order = relationship("Order", back_populates="items")
