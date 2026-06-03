from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db_session
from app.db.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPairResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    UserResponse,
)
from app.schemas.common import ApiMessage
from app.services.auth import (
    change_password,
    disable_2fa,
    enable_2fa,
    login,
    logout,
    refresh,
    setup_2fa,
)

router = APIRouter()


@router.post("/login", response_model=TokenPairResponse)
async def login_endpoint(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    return await login(
        session,
        username=payload.username,
        password=payload.password,
        otp_code=payload.otp_code,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_endpoint(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    return await refresh(session, payload.refresh_token)


@router.post("/logout", response_model=ApiMessage)
async def logout_endpoint(
    payload: LogoutRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    await logout(session, payload.refresh_token)
    return ApiMessage(message="Logged out")


@router.post("/password/change", response_model=ApiMessage)
async def change_password_endpoint(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    await change_password(session, current_user, payload.current_password, payload.new_password)
    return ApiMessage(message="Password changed")


@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa_endpoint(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TOTPSetupResponse:
    return await setup_2fa(session, current_user)


@router.post("/2fa/enable", response_model=ApiMessage)
async def enable_2fa_endpoint(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    await enable_2fa(session, current_user, payload.code)
    return ApiMessage(message="2FA enabled")


@router.post("/2fa/disable", response_model=ApiMessage)
async def disable_2fa_endpoint(
    payload: TOTPVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ApiMessage:
    await disable_2fa(session, current_user, payload.code)
    return ApiMessage(message="2FA disabled")


@router.get("/me", response_model=UserResponse)
async def me_endpoint(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        phone_number=current_user.phone_number,
        full_name=current_user.full_name,
        roles=[r.code.value for r in current_user.roles],
        is_active=current_user.is_active,
        must_change_password=current_user.must_change_password,
    )
