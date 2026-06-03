from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import get_redis_client
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.logging import bind_log_context
from app.core.security import decode_token
from app.db.enums import RoleCode
from app.db.models import User

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_redis() -> Redis:
    return get_redis_client()


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject")

    stmt = select(User).where(User.id == UUID(user_id)).options(selectinload(User.roles))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
    request.state.user_id = str(user.id)
    bind_log_context(
        user_id=str(user.id),
        roles=[role.code.value for role in user.roles],
    )
    return user


def require_roles(*allowed: RoleCode) -> Callable[[User], User]:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        user_roles = {role.code for role in user.roles}
        if not any(role in user_roles for role in allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


async def verify_service_token(request: Request, x_service_token: str = Header(...)) -> dict:
    try:
        payload = jwt.decode(
            x_service_token,
            settings.service_token_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token") from exc

    if payload.get("service") != "tg-service":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unexpected service identity")
    request.state.service_name = str(payload.get("service"))
    bind_log_context(service_name=str(payload.get("service")))
    return payload


async def tg_rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis),
    x_telegram_id: str | None = Header(default=None),
) -> None:
    identifier = x_telegram_id or request.client.host if request.client else "unknown"
    key = f"tg_rate_limit:{identifier}"

    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > settings.rate_limit_tg_per_minute:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        # Fallback to best-effort mode if Redis is temporarily unavailable.
        return
