import os

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class CurrentUser:
    def __init__(self, user_id: int, username: str) -> None:
        self.user_id = user_id
        self.username = username


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
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


def require_auth(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Dependency: проверяет JWT (выпущенный auth_service) и возвращает пользователя."""
    token = _extract_token(authorization)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("uid")
    username = payload.get("sub")
    if not isinstance(user_id, int) or not isinstance(username, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный токен",
        )
    return CurrentUser(user_id=user_id, username=username)


__all__ = ["CurrentUser", "require_auth", "Depends"]
