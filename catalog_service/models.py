from sqlalchemy import JSON, Column, Float, Integer, LargeBinary, String, Text

from .database import Base


class Item(Base):
    __tablename__ = "item"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False, default="")
    feature_1 = Column(String(255), nullable=True)
    feature_2 = Column(Float, nullable=True)
    feature_3 = Column(String(255), nullable=True)
    features = Column(JSON, nullable=False, default=dict)
    photo = Column(LargeBinary, nullable=True)
    price = Column(Float, nullable=False, default=0)
    stock = Column(Integer, nullable=False, default=0)
