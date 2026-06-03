from __future__ import annotations

from datetime import UTC
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    build_totp_uri,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_session_id,
    generate_totp_secret,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_totp_code,
)
from app.core.time import utc_now
from app.db.models import LoginAudit, RefreshSession, User
from app.schemas.auth import TokenPairResponse, TOTPSetupResponse
from app.services.audit import log_audit


def _http_unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _insert_login_audit(
    session: AsyncSession,
    username: str,
    success: bool,
    user_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    session.add(
        LoginAudit(
            user_id=user_id,
            username=username,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )


async def issue_token_pair(
    session: AsyncSession,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
    *,
    audit_action: str,
) -> TokenPairResponse:
    roles = [r.code.value for r in user.roles]
    access_token, access_exp = create_access_token(
        user_id=str(user.id),
        roles=roles,
        password_change_required=user.must_change_password,
    )

    session_id = generate_session_id()
    refresh_token, refresh_exp = create_refresh_token(user_id=str(user.id), session_id=session_id)
    session.add(
        RefreshSession(
            user_id=user.id,
            session_id=session_id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_exp,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    )
    await _insert_login_audit(
        session,
        username=user.username,
        success=True,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await log_audit(
        session,
        actor_user_id=user.id,
        action=audit_action,
        entity_type="user",
        entity_id=str(user.id),
    )
    await session.commit()

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
        password_change_required=user.must_change_password,
    )


async def login(
    session: AsyncSession,
    username: str,
    password: str,
    otp_code: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> TokenPairResponse:
    stmt = select(User).where(User.username == username).options(selectinload(User.roles))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user:
        await _insert_login_audit(session, username=username, success=False, ip_address=ip_address, user_agent=user_agent)
        await session.commit()
        raise _http_unauthorized("Invalid credentials")

    if not user.is_active or user.is_archived:
        await _insert_login_audit(
            session,
            username=username,
            success=False,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        raise _http_unauthorized("User inactive")

    if not verify_password(password, user.password_hash):
        await _insert_login_audit(
            session,
            username=username,
            success=False,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        raise _http_unauthorized("Invalid credentials")

    if user.is_2fa_enabled and (
        not otp_code or not user.totp_secret or not verify_totp_code(user.totp_secret, otp_code)
    ):
        await _insert_login_audit(
            session,
            username=username,
            success=False,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await session.commit()
        raise _http_unauthorized("Invalid one-time code")

    return await issue_token_pair(
        session,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
        audit_action="auth.login",
    )


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPairResponse:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise _http_unauthorized("Wrong token type")

    session_id = payload.get("sid")
    user_id = payload.get("sub")
    if not session_id or not user_id:
        raise _http_unauthorized("Malformed token")

    stmt = (
        select(RefreshSession)
        .where(
            RefreshSession.session_id == session_id,
            RefreshSession.token_hash == hash_refresh_token(refresh_token),
            RefreshSession.revoked_at.is_(None),
        )
        .limit(1)
    )
    refresh_session = (await session.execute(stmt)).scalar_one_or_none()
    if not refresh_session:
        raise _http_unauthorized("Session not found")

    expires_at = refresh_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < utc_now():
        raise _http_unauthorized("Refresh token expired")

    user_stmt = select(User).where(User.id == UUID(user_id)).options(selectinload(User.roles))
    user = (await session.execute(user_stmt)).scalar_one_or_none()
    if not user or not user.is_active:
        raise _http_unauthorized("User inactive")

    refresh_session.revoked_at = utc_now()

    roles = [role.code.value for role in user.roles]
    access_token, access_exp = create_access_token(
        user_id=str(user.id),
        roles=roles,
        password_change_required=user.must_change_password,
    )
    new_sid = generate_session_id()
    new_refresh_token, refresh_exp = create_refresh_token(user_id=str(user.id), session_id=new_sid)
    session.add(
        RefreshSession(
            user_id=user.id,
            session_id=new_sid,
            token_hash=hash_refresh_token(new_refresh_token),
            expires_at=refresh_exp,
        )
    )
    await session.commit()

    return TokenPairResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
        password_change_required=user.must_change_password,
    )


async def logout(session: AsyncSession, refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        return

    sid = payload.get("sid")
    if not sid:
        return

    stmt = select(RefreshSession).where(RefreshSession.session_id == sid, RefreshSession.revoked_at.is_(None))
    refresh_session = (await session.execute(stmt)).scalar_one_or_none()
    if refresh_session:
        refresh_session.revoked_at = utc_now()
        await session.commit()


async def change_password(
    session: AsyncSession,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wrong current password")

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await log_audit(
        session,
        actor_user_id=user.id,
        action="auth.password_change",
        entity_type="user",
        entity_id=str(user.id),
    )
    await session.commit()


async def setup_2fa(session: AsyncSession, user: User) -> TOTPSetupResponse:
    secret = generate_totp_secret()
    user.totp_secret = secret
    user.is_2fa_enabled = False
    await session.commit()
    return TOTPSetupResponse(
        secret=secret,
        provisioning_uri=build_totp_uri(secret=secret, username=user.username),
    )


async def enable_2fa(session: AsyncSession, user: User, code: str) -> None:
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA not initialized")
    if not verify_totp_code(user.totp_secret, code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    user.is_2fa_enabled = True
    await log_audit(
        session,
        actor_user_id=user.id,
        action="auth.2fa_enable",
        entity_type="user",
        entity_id=str(user.id),
    )
    await session.commit()


async def disable_2fa(session: AsyncSession, user: User, code: str) -> None:
    if user.is_2fa_enabled and (
        not user.totp_secret or not verify_totp_code(user.totp_secret, code)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    user.totp_secret = None
    user.is_2fa_enabled = False
    await log_audit(
        session,
        actor_user_id=user.id,
        action="auth.2fa_disable",
        entity_type="user",
        entity_id=str(user.id),
    )
    await session.commit()
