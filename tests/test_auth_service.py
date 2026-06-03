from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.db.enums import RoleCode
from app.db.models import RefreshSession, Role, User
from app.services.auth import login, logout, refresh


@pytest.mark.asyncio
async def test_login_refresh_logout_flow(session):
    role = Role(code=RoleCode.ADMIN, name="Admin")
    user = User(
        username="admin_test",
        full_name="Admin Test",
        password_hash=hash_password("Password123!"),
        must_change_password=False,
    )
    user.roles.append(role)
    session.add_all([role, user])
    await session.commit()

    tokens = await login(
        session,
        username="admin_test",
        password="Password123!",
        otp_code=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.password_change_required is False

    stored = (await session.execute(select(RefreshSession))).scalars().all()
    assert len(stored) == 1

    refreshed = await refresh(session, tokens.refresh_token)
    assert refreshed.access_token != tokens.access_token

    await logout(session, refreshed.refresh_token)
    active_sessions = (
        await session.execute(select(RefreshSession).where(RefreshSession.revoked_at.is_(None)))
    ).scalars().all()
    assert len(active_sessions) == 0


def test_verify_password_supports_existing_passlib_pbkdf2_hashes() -> None:
    old_hash = "$pbkdf2-sha256$29000$HoMQIsQ4B0CoNeY8Z6x1bg$5.8/wiMK1uh3kfO3ystr3j6ivne6UH.ElCJmqCbP71g"
    assert verify_password("Password123!", old_hash) is True
    assert verify_password("WrongPassword", old_hash) is False
