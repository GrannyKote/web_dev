from collections.abc import Generator

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal, init_db
from .security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_access_token,
    hash_password,
    verify_password,
)

app = FastAPI(title="Auth Service")
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

init_db()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _token_from_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не передан токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ожидается заголовок 'Authorization: Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return parts[1].strip()


def to_user_response(user: models.User) -> schemas.UserResponse:
    return schemas.UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    )


@app.post(
    "/auth/register",
    response_model=schemas.TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким username уже существует",
        )

    user = models.User(
        username=payload.username,
        email=str(payload.email) if payload.email else None,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не удалось создать пользователя (конфликт уникальности)",
        ) from exc
    db.refresh(user)

    token, expires_in = create_access_token(subject=user.username, user_id=user.id)
    return schemas.TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=to_user_response(user),
    )


@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    token, expires_in = create_access_token(subject=user.username, user_id=user.id)
    return schemas.TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=to_user_response(user),
    )


@app.get("/auth/me", response_model=schemas.UserResponse)
def me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> schemas.UserResponse:
    token = _token_from_header(authorization)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        ) from exc
    user_id = payload.get("uid")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Некорректный токен")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return to_user_response(user)


@app.get("/auth/verify")
def verify_token(authorization: str | None = Header(default=None)) -> dict:
    """Проверка валидности токена (используется gateway и другими сервисами)."""
    token = _token_from_header(authorization)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        ) from exc
    return {
        "valid": True,
        "user_id": payload.get("uid"),
        "username": payload.get("sub"),
    }
