from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import BigInteger, select

from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.time import utc_now
from app.db.enums import BindingRequestStatus, LessonStatus, RoleCode
from app.db.models import (
    BroadcastRecipient,
    Discipline,
    Group,
    GroupTelegramChat,
    InviteActivation,
    Lesson,
    NotificationOutbox,
    RefreshSession,
    Role,
    StudentGroupMembership,
    TelegramAccount,
    TelegramBindingRequest,
    User,
)
from app.main import app

settings = get_settings()
LARGE_TELEGRAM_ID = 5_469_004_328


@pytest.fixture()
async def api_client(session):
    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def build_service_token() -> str:
    return jwt.encode(
        {
            "service": "tg-service",
            "iat": utc_now(),
            "exp": utc_now() + timedelta(minutes=5),
        },
        settings.service_token_secret,
        algorithm=settings.jwt_algorithm,
    )


def tg_headers(telegram_id: int = 100500) -> dict[str, str]:
    return {"X-Service-Token": build_service_token(), "X-Telegram-Id": str(telegram_id)}


@pytest.mark.asyncio
async def test_tg_bootstrap_and_exchange_for_linked_student(session, api_client):
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    student = User(username="st_linked", full_name="Linked Student", password_hash="x", must_change_password=False)
    student.roles.append(student_role)
    session.add_all([student_role, student])
    await session.flush()
    session.add(TelegramAccount(user_id=student.id, telegram_id=100500, username="linked"))
    await session.commit()

    bootstrap = await api_client.get("/api/v1/tg/bootstrap/100500", headers=tg_headers())
    assert bootstrap.status_code == 200
    payload = bootstrap.json()
    assert payload["status"] == "linked"
    assert payload["user"]["username"] == "st_linked"
    assert payload["user"]["roles"] == ["student"]

    exchange = await api_client.post(
        "/api/v1/tg/auth/exchange",
        headers=tg_headers(),
        json={"telegram_id": 100500},
    )
    assert exchange.status_code == 200
    exchange_payload = exchange.json()
    assert exchange_payload["access_token"]
    assert exchange_payload["refresh_token"]
    assert exchange_payload["user"]["full_name"] == "Linked Student"

    sessions = (await session.execute(RefreshSession.__table__.select())).all()
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_tg_bootstrap_and_exchange_support_large_telegram_id(session, api_client):
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    student = User(username="st_large_tg", full_name="Large TG Student", password_hash="x", must_change_password=False)
    student.roles.append(student_role)
    session.add_all([student_role, student])
    await session.flush()
    session.add(TelegramAccount(user_id=student.id, telegram_id=LARGE_TELEGRAM_ID, username="large_linked"))
    await session.commit()

    bootstrap = await api_client.get(f"/api/v1/tg/bootstrap/{LARGE_TELEGRAM_ID}", headers=tg_headers(LARGE_TELEGRAM_ID))
    assert bootstrap.status_code == 200
    assert bootstrap.json()["status"] == "linked"

    exchange = await api_client.post(
        "/api/v1/tg/auth/exchange",
        headers=tg_headers(LARGE_TELEGRAM_ID),
        json={"telegram_id": LARGE_TELEGRAM_ID},
    )
    assert exchange.status_code == 200
    assert exchange.json()["user"]["username"] == "st_large_tg"


@pytest.mark.asyncio
async def test_tg_bootstrap_returns_binding_request_status_and_fields(session, api_client):
    request = TelegramBindingRequest(
        telegram_id=100501,
        telegram_username="pending_user",
        full_name="Pending Student",
        group_code="SE-101",
        note="first flow",
        status=BindingRequestStatus.PENDING,
    )
    session.add(request)
    await session.commit()

    response = await api_client.get("/api/v1/tg/bootstrap/100501", headers=tg_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["requested_full_name"] == "Pending Student"
    assert payload["group_code"] == "SE-101"
    assert payload["note"] == "first flow"


@pytest.mark.asyncio
async def test_tg_bootstrap_returns_link_required_and_rejected_states(session, api_client):
    empty_response = await api_client.get("/api/v1/tg/bootstrap/199999", headers=tg_headers())
    assert empty_response.status_code == 200
    assert empty_response.json()["status"] == "link_required"

    rejected_request = TelegramBindingRequest(
        telegram_id=100504,
        telegram_username="rejected_user",
        full_name="Rejected Student",
        status=BindingRequestStatus.REJECTED,
        resolved_at=utc_now(),
    )
    session.add(rejected_request)
    await session.commit()

    rejected_response = await api_client.get("/api/v1/tg/bootstrap/100504", headers=tg_headers())
    assert rejected_response.status_code == 200
    assert rejected_response.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_tg_exchange_supports_linked_teacher_and_binding_requests_are_idempotent(session, api_client):
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    teacher = User(username="teacher_linked", full_name="Teacher Linked", password_hash="x", must_change_password=False)
    teacher.roles.append(teacher_role)
    session.add_all([teacher_role, teacher])
    await session.flush()
    session.add(TelegramAccount(user_id=teacher.id, telegram_id=100502, username="teacher"))
    await session.commit()

    exchange = await api_client.post(
        "/api/v1/tg/auth/exchange",
        headers=tg_headers(),
        json={"telegram_id": 100502},
    )
    assert exchange.status_code == 200
    assert exchange.json()["user"]["roles"] == ["teacher"]

    create_payload = {
        "telegram_id": 100503,
        "telegram_username": "new_student",
        "full_name": "New Student",
        "group_code": "SE-102",
        "note": "Needs approval",
    }
    first = await api_client.post("/api/v1/tg/binding-requests", headers=tg_headers(), json=create_payload)
    second = await api_client.post("/api/v1/tg/binding-requests", headers=tg_headers(), json=create_payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["message"] == "Request already pending"

    status_response = await api_client.get("/api/v1/tg/binding-requests/100503", headers=tg_headers())
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "pending"
    assert status_payload["group_code"] == "SE-102"
    assert status_payload["note"] == "Needs approval"


@pytest.mark.asyncio
async def test_tg_student_chat_endpoints_return_schedule_faq_and_assistant_reply(session, api_client, faq_storage):
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    student = User(username="tg_student", full_name="TG Student", password_hash="x", must_change_password=False)
    teacher = User(username="tg_teacher", full_name="TG Teacher", password_hash="x", must_change_password=False)
    student.roles.append(student_role)
    teacher.roles.append(teacher_role)

    group = Group(code="SE-201", name="SE-201")
    discipline = Discipline(code="DB", name="Databases")

    session.add_all([student_role, teacher_role, student, teacher, group, discipline])
    await session.flush()
    session.add(TelegramAccount(user_id=student.id, telegram_id=100700, username="tg_student"))
    session.add(
        StudentGroupMembership(
            student_id=student.id,
            group_id=group.id,
            start_date=utc_now().date(),
            is_primary=True,
        )
    )
    session.add(
        Lesson(
            group_id=group.id,
            discipline_id=discipline.id,
            teacher_id=teacher.id,
            starts_at=utc_now() + timedelta(days=1),
            ends_at=utc_now() + timedelta(days=1, hours=1),
            status=LessonStatus.PLANNED,
            window_start_offset_minutes=-5,
            window_duration_minutes=20,
            late_threshold_minutes=10,
            room="A-101",
        )
    )
    await session.commit()
    faq_path = faq_storage["source_dir"] / "Регистрация" / "Как привязать Telegram.md"
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    faq_path.write_text("Откройте mini app и отправьте заявку на привязку.", encoding="utf-8")

    schedule = await api_client.get("/api/v1/tg/student/schedule/100700", headers=tg_headers(100700))
    assert schedule.status_code == 200
    schedule_payload = schedule.json()
    assert len(schedule_payload) == 1
    assert schedule_payload[0]["discipline_name"] == "Databases"

    faq_response = await api_client.get(
        "/api/v1/tg/student/faq/100700",
        headers=tg_headers(100700),
        params={"query": "telegram"},
    )
    assert faq_response.status_code == 200
    faq_payload = faq_response.json()
    assert faq_payload[0]["category_name"] == "Регистрация"

    assistant = await api_client.post(
        "/api/v1/tg/assistant/reply",
        headers=tg_headers(100700),
        json={"telegram_id": 100700, "message": "telegram"},
    )
    assert assistant.status_code == 200
    assistant_payload = assistant.json()
    assert "mini app" in assistant_payload["message"].lower()
    assert assistant_payload["used_faq_ids"]
    assert assistant_payload["status"] == "linked"


@pytest.mark.asyncio
async def test_tg_teacher_chat_endpoints_return_lessons_roster_and_qr(session, api_client):
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    teacher = User(username="teacher_tg", full_name="Teacher TG", password_hash="x", must_change_password=False)
    student = User(username="student_tg", full_name="Student TG", password_hash="x", must_change_password=False)
    teacher.roles.append(teacher_role)
    student.roles.append(student_role)

    group = Group(code="SE-301", name="SE-301")
    discipline = Discipline(code="AI", name="AI Fundamentals")

    session.add_all([teacher_role, student_role, teacher, student, group, discipline])
    await session.flush()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=utc_now() + timedelta(days=1),
        ends_at=utc_now() + timedelta(days=1, hours=1),
        status=LessonStatus.PLANNED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=10,
        room="B-204",
    )
    session.add_all(
        [
            lesson,
            TelegramAccount(user_id=teacher.id, telegram_id=100701, username="teacher_tg"),
            TelegramAccount(user_id=student.id, telegram_id=100702, username="student_tg"),
            GroupTelegramChat(group_id=group.id, telegram_chat_id=-100555000111, title="SE-301 chat"),
            StudentGroupMembership(
                student_id=student.id,
                group_id=group.id,
                start_date=utc_now().date(),
                is_primary=True,
            ),
        ]
    )
    await session.commit()

    lessons = await api_client.get("/api/v1/tg/teacher/lessons/100701", headers=tg_headers(100701))
    assert lessons.status_code == 200
    lessons_payload = lessons.json()
    assert len(lessons_payload) == 1
    assert lessons_payload[0]["group_name"] == "SE-301"

    roster = await api_client.get(
        f"/api/v1/tg/teacher/lessons/100701/{lesson.id}/attendance",
        headers=tg_headers(100701),
    )
    assert roster.status_code == 200
    roster_payload = roster.json()
    assert roster_payload["students"][0]["full_name"] == "Student TG"

    qr = await api_client.post(
        "/api/v1/tg/teacher/qr/generate",
        headers=tg_headers(100701),
        json={"telegram_id": 100701, "lesson_id": str(lesson.id)},
    )
    assert qr.status_code == 200
    qr_payload = qr.json()
    assert qr_payload["token"]
    assert "start=qr_" in qr_payload["deeplink"]

    broadcast = await api_client.post(
        "/api/v1/tg/teacher/broadcasts",
        headers=tg_headers(100701),
        json={"telegram_id": 100701, "group_id": str(group.id), "message": "Проверьте обновление"},
    )
    assert broadcast.status_code == 200

    outbox_rows = (
        await session.execute(select(NotificationOutbox).where(NotificationOutbox.event_type == "teacher_broadcast"))
    ).scalars().all()
    assert len(outbox_rows) == 2


def test_telegram_identifier_columns_use_bigint() -> None:
    columns = (
        TelegramAccount.__table__.c.telegram_id,
        InviteActivation.__table__.c.telegram_id,
        TelegramBindingRequest.__table__.c.telegram_id,
        NotificationOutbox.__table__.c.recipient_telegram_id,
        BroadcastRecipient.__table__.c.telegram_id,
    )
    assert all(isinstance(column.type, BigInteger) for column in columns)
