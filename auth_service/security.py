import os
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(*, subject: str, user_id: int, extra: dict | None = None) -> tuple[str, int]:
    """Возвращает (token, expires_in_seconds)."""
    expires_delta = timedelta(minutes=JWT_EXPIRES_MINUTES)
    expire_at = datetime.now(timezone.utc) + expires_delta
    payload: dict = {
        "sub": subject,
        "uid": user_id,
        "exp": expire_at,
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())
