import base64
from collections.abc import Generator

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal, init_db

app = FastAPI(title="Catalog Service")

init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def decode_photo(photo: str | None) -> bytes | None:
    if not photo:
        return None
    try:
        return base64.b64decode(photo, validate=True)
    except Exception:
        return photo.encode("utf-8")


def encode_photo(photo: bytes | None) -> str | None:
    if photo is None:
        return None
    return base64.b64encode(photo).decode("utf-8")


def to_response(item: models.Item) -> schemas.ItemResponse:
    return schemas.ItemResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        feature_1=item.feature_1,
        feature_2=item.feature_2,
        feature_3=item.feature_3,
        features=item.features or {},
        photo=encode_photo(item.photo),
        price=item.price,
        stock=item.stock,
    )


@app.get("/catalog", response_model=list[schemas.ItemResponse])
def get_items(
    feature_1: str | None = None,
    feature_2_from: float | None = None,
    feature_2_to: float | None = None,
    feature_3: str | None = None,
    db: Session = Depends(get_db),
) -> list[schemas.ItemResponse]:
    query = db.query(models.Item)
    if feature_1 is not None:
        query = query.filter(models.Item.feature_1 == feature_1)
    if feature_2_from is not None:
        query = query.filter(models.Item.feature_2 >= feature_2_from)
    if feature_2_to is not None:
        query = query.filter(models.Item.feature_2 <= feature_2_to)
    if feature_3 is not None:
        query = query.filter(models.Item.feature_3 == feature_3)
    return [to_response(item) for item in query.order_by(models.Item.id).all()]


@app.get("/catalog/{item_id}", response_model=schemas.ItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)) -> schemas.ItemResponse:
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return to_response(item)


@app.post("/catalog", response_model=schemas.ItemResponse)
def add_item(payload: schemas.ItemCreate, db: Session = Depends(get_db)) -> schemas.ItemResponse:
    item = models.Item(
        name=payload.name,
        description=payload.description or "",
        feature_1=payload.feature_1,
        feature_2=payload.feature_2,
        feature_3=payload.feature_3,
        features=payload.features or {},
        photo=decode_photo(payload.photo),
        price=payload.price if payload.price is not None else 0,
        stock=payload.stock if payload.stock is not None else 0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return to_response(item)


@app.put("/catalog/{item_id}", response_model=schemas.ItemResponse)
def update_item(
    item_id: int,
    payload: schemas.ItemUpdate,
    db: Session = Depends(get_db),
) -> schemas.ItemResponse:
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    update_values = payload.model_dump(exclude_unset=True)
    if "photo" in update_values:
        item.photo = decode_photo(update_values.pop("photo"))
    for key, value in update_values.items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return to_response(item)


@app.delete("/catalog/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    db.delete(item)
    db.commit()
