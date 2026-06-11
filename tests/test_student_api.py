from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.db import get_db_session
from app.core.time import utc_now
from app.db.enums import (
    AbsenceReasonType,
    AttendanceSource,
    AttendanceStatus,
    LessonStatus,
    ModerationStatus,
    RoleCode,
)
from app.db.models import (
    AbsenceAttachment,
    AbsenceReason,
    AttendanceRecord,
    Discipline,
    Group,
    Lesson,
    Role,
    StudentGroupMembership,
    User,
)
from app.main import app
from app.services.attendance import (
    build_dynamic_qr_token,
    create_dynamic_qr_session,
    generate_qr_token,
)


@pytest.fixture()
async def api_client(session):
    async def override_db():
        yield session

    app.dependency_overrides[get_db_session] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def override_user(user: User) -> None:
    async def _override_user():
        return user

    app.dependency_overrides[get_current_user] = _override_user


async def _seed_student_lesson(session, *, membership_group: Group | None = None):
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    student = User(username="student_api", full_name="Student API", password_hash="x", must_change_password=False)
    teacher = User(username="teacher_api", full_name="Teacher API", password_hash="x", must_change_password=False)
    student.roles.append(role_student)
    teacher.roles.append(role_teacher)
    lesson_group = Group(code="ST-1", name="Student Group")
    assigned_group = membership_group or lesson_group
    discipline = Discipline(code="DS-1", name="Discrete Math")
    session.add_all([role_student, role_teacher, student, teacher, lesson_group, assigned_group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=lesson_group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=59),
        room="A-101",
        status=LessonStatus.IN_PROGRESS,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(lesson)
    await session.flush()
    session.add(
        StudentGroupMembership(
            student_id=student.id,
            group_id=assigned_group.id,
            start_date=(now - timedelta(days=1)).date(),
            end_date=None,
            is_primary=True,
        )
    )
    await session.commit()
    return student, teacher, lesson_group, discipline, lesson


@pytest.mark.asyncio
async def test_student_schedule_history_and_absence_reasons_are_enriched(session, api_client):
    student, teacher, group, discipline, lesson = await _seed_student_lesson(session)
    override_user(student)

    session.add(
        AttendanceRecord(
            lesson_id=lesson.id,
            student_id=student.id,
            status=AttendanceStatus.LATE,
            source=AttendanceSource.TEACHER_MANUAL,
            marked_at=lesson.starts_at + timedelta(minutes=5),
            marked_by=teacher.id,
            correction_reason="Late due to traffic",
        )
    )
    await session.flush()

    reason = AbsenceReason(
        lesson_id=lesson.id,
        student_id=student.id,
        reason_type=AbsenceReasonType.ILLNESS,
        comment="Doctor note",
        is_predeclared=False,
        moderation_status=ModerationStatus.PENDING,
    )
    session.add(reason)
    await session.flush()
    session.add(
        AbsenceAttachment(
            reason_id=reason.id,
            file_name="note.pdf",
            file_path="/tmp/note.pdf",
            content_type="application/pdf",
            size_bytes=128,
        )
    )
    await session.commit()

    schedule = await api_client.get("/api/v1/student/schedule")
    assert schedule.status_code == 200
    schedule_item = schedule.json()[0]
    assert schedule_item["group_name"] == "Student Group"
    assert schedule_item["discipline_name"] == "Discrete Math"
    assert schedule_item["teacher_name"] == "Teacher API"
    assert schedule_item["attendance_window_opens_at"]
    assert schedule_item["attendance_window_closes_at"]

    history = await api_client.get(
        "/api/v1/student/attendance/history",
        params={"date_from": str((utc_now() - timedelta(days=1)).date()), "date_to": str((utc_now() + timedelta(days=1)).date())},
    )
    assert history.status_code == 200
    history_item = history.json()[0]
    assert history_item["group_code"] == group.code
    assert history_item["discipline_code"] == discipline.code
    assert history_item["teacher_name"] == "Teacher API"
    assert history_item["source"] == "teacher_manual"
    assert history_item["correction_reason"] == "Late due to traffic"

    reasons = await api_client.get("/api/v1/student/absence-reasons")
    assert reasons.status_code == 200
    reason_item = reasons.json()[0]
    assert reason_item["discipline_name"] == "Discrete Math"
    assert reason_item["attachments"][0]["file_name"] == "note.pdf"


@pytest.mark.asyncio
async def test_student_can_upload_absence_reason_attachment(session, api_client, monkeypatch, tmp_path):
    student, _teacher, _group, _discipline, lesson = await _seed_student_lesson(session)
    override_user(student)
    monkeypatch.setattr("app.services.storage.settings.attachments_dir", str(tmp_path / "attachments"))

    response = await api_client.post(
        "/api/v1/student/absence-reasons",
        data={
            "lesson_id": str(lesson.id),
            "reason_type": AbsenceReasonType.ILLNESS.value,
            "comment": "Doctor note attached",
            "is_predeclared": "false",
        },
        files={"file": ("note.pdf", b"%PDF-1.4 test", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["attachment"]["file_name"] == "note.pdf"
    assert payload["attachment"]["content_type"] == "application/pdf"

    attachment = (await session.execute(select(AbsenceAttachment))).scalar_one()
    assert attachment.file_name == "note.pdf"
    assert attachment.content_type == "application/pdf"
    assert attachment.size_bytes == len(b"%PDF-1.4 test")
    assert tmp_path.joinpath("attachments").exists()
    assert tmp_path.joinpath("attachments", Path(attachment.file_path).name).read_bytes() == b"%PDF-1.4 test"


@pytest.mark.asyncio
async def test_student_mark_qr_attendance_supports_static_and_dynamic_tokens(session, api_client):
    student, teacher, _group, _discipline, lesson = await _seed_student_lesson(session)
    override_user(student)

    static_token, _token_row = await generate_qr_token(session, lesson_id=lesson.id, teacher_id=teacher.id)
    static_response = await api_client.post(
        "/api/v1/student/attendance/mark-qr",
        json={"qr_token": f"https://t.me/universe_test_bot?start=qr_{static_token}"},
    )
    assert static_response.status_code == 200
    assert static_response.json()["status"] in {"present", "late"}

    duplicate = await api_client.post("/api/v1/student/attendance/mark-qr", json={"qr_token": static_token})
    assert duplicate.status_code == 409

    # Create a second lesson for dynamic QR validation.
    now = utc_now()
    dynamic_lesson = Lesson(
        group_id=lesson.group_id,
        discipline_id=lesson.discipline_id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=60),
        room="A-102",
        status=LessonStatus.IN_PROGRESS,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(dynamic_lesson)
    await session.commit()

    qr_session = await create_dynamic_qr_session(session, lesson_id=dynamic_lesson.id, teacher_id=teacher.id)
    dynamic_token, _slot = build_dynamic_qr_token(qr_session)
    dynamic_response = await api_client.post(
        "/api/v1/student/attendance/mark-qr",
        json={"qr_token": f"tg://resolve?domain=universe_test_bot&start=qr_{dynamic_token}"},
    )
    assert dynamic_response.status_code == 200

    second_student = User(
        username="student_dynamic_second",
        full_name="Second Dynamic Student",
        password_hash="x",
        must_change_password=False,
    )
    second_student.roles.append(student.roles[0])
    session.add(second_student)
    await session.flush()
    session.add(
        StudentGroupMembership(
            student_id=second_student.id,
            group_id=dynamic_lesson.group_id,
            start_date=now.date(),
            is_primary=True,
        )
    )
    await session.commit()

    override_user(second_student)
    reused_token_response = await api_client.post(
        "/api/v1/student/attendance/mark-qr",
        json={"qr_token": dynamic_token},
    )
    assert reused_token_response.status_code == 409

    next_dynamic_token, _next_slot = build_dynamic_qr_token(qr_session)
    assert next_dynamic_token != dynamic_token
    next_token_response = await api_client.post(
        "/api/v1/student/attendance/mark-qr",
        json={"qr_token": next_dynamic_token},
    )
    assert next_token_response.status_code == 200


@pytest.mark.asyncio
async def test_student_mark_qr_rejects_closed_window_and_foreign_group(session, api_client):
    other_group = Group(code="OTHER-1", name="Other Group")
    session.add(other_group)
    await session.flush()

    student, teacher, _group, discipline, _lesson = await _seed_student_lesson(session, membership_group=other_group)
    override_user(student)

    now = utc_now()
    closed_lesson = Lesson(
        group_id=other_group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(hours=2),
        ends_at=now - timedelta(hours=1),
        room="B-201",
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    foreign_group = Group(code="FOREIGN-1", name="Foreign Group")
    session.add(foreign_group)
    await session.flush()
    foreign_lesson = Lesson(
        group_id=foreign_group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=59),
        room="B-202",
        status=LessonStatus.IN_PROGRESS,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(foreign_lesson)
    session.add(closed_lesson)
    await session.commit()

    closed_token, _ = await generate_qr_token(session, lesson_id=closed_lesson.id, teacher_id=teacher.id)
    closed_response = await api_client.post("/api/v1/student/attendance/mark-qr", json={"qr_token": closed_token})
    assert closed_response.status_code == 400

    foreign_token, _ = await generate_qr_token(session, lesson_id=foreign_lesson.id, teacher_id=teacher.id)
    foreign_response = await api_client.post("/api/v1/student/attendance/mark-qr", json={"qr_token": foreign_token})
    assert foreign_response.status_code == 403


@pytest.mark.asyncio
async def test_student_faq_reads_markdown_backed_content(session, api_client, faq_storage):
    student, _teacher, _group, _discipline, _lesson = await _seed_student_lesson(session)
    override_user(student)

    faq_path = faq_storage["source_dir"] / "general" / "telegram-binding.md"
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    faq_path.write_text("Откройте mini app и отправьте заявку на привязку.", encoding="utf-8")

    response = await api_client.get("/api/v1/student/faq", params={"query": "telegram"})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["category_name"] == "general"
    assert payload[0]["question"] == "telegram-binding"
