from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

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
    TeacherAssignment,
    User,
)
from app.main import app


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


@pytest.mark.asyncio
async def test_teacher_groups_and_lessons_include_display_fields(session, api_client):
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    teacher = User(username="teacher_api", full_name="Teacher API", password_hash="x", must_change_password=False)
    teacher.roles.append(role_teacher)

    group = Group(code="TG-1", name="Teacher Group")
    discipline = Discipline(code="TD-1", name="Databases")
    session.add_all([role_teacher, teacher, group, discipline])
    await session.flush()

    session.add(
        TeacherAssignment(
            teacher_id=teacher.id,
            discipline_id=discipline.id,
            group_id=group.id,
            is_active=True,
        )
    )

    now = utc_now()
    session.add(
        Lesson(
            group_id=group.id,
            discipline_id=discipline.id,
            teacher_id=teacher.id,
            starts_at=now,
            ends_at=now + timedelta(hours=1, minutes=30),
            room="B-201",
            status=LessonStatus.PLANNED,
            window_start_offset_minutes=-5,
            window_duration_minutes=20,
            late_threshold_minutes=20,
        )
    )
    await session.commit()

    override_user(teacher)

    groups_response = await api_client.get("/api/v1/teacher/groups")
    assert groups_response.status_code == 200
    assert groups_response.json() == [{"id": str(group.id), "code": "TG-1", "name": "Teacher Group"}]

    lessons_response = await api_client.get("/api/v1/teacher/lessons")
    assert lessons_response.status_code == 200
    payload = lessons_response.json()
    assert payload[0]["group_code"] == "TG-1"
    assert payload[0]["group_name"] == "Teacher Group"
    assert payload[0]["discipline_code"] == "TD-1"
    assert payload[0]["discipline_name"] == "Databases"
    assert payload[0]["room"] == "B-201"


@pytest.mark.asyncio
async def test_teacher_qr_endpoints_generate_static_and_dynamic_sessions(session, api_client):
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    teacher = User(username="teacher_qr", full_name="Teacher QR", password_hash="x", must_change_password=False)
    teacher.roles.append(role_teacher)

    group = Group(code="TG-QR", name="Teacher QR Group")
    discipline = Discipline(code="TD-QR", name="Discrete Math")
    session.add_all([role_teacher, teacher, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(hours=1),
        room="QR-101",
        status=LessonStatus.IN_PROGRESS,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(lesson)
    await session.commit()

    override_user(teacher)

    static_response = await api_client.post("/api/v1/teacher/qr/generate", json={"lesson_id": str(lesson.id)})
    assert static_response.status_code == 200
    static_payload = static_response.json()
    assert static_payload["token"]
    assert "start=qr_" in static_payload["deeplink"]
    assert static_payload["expires_at"]

    dynamic_response = await api_client.post("/api/v1/teacher/qr/sessions/start", json={"lesson_id": str(lesson.id)})
    assert dynamic_response.status_code == 200
    dynamic_payload = dynamic_response.json()
    assert dynamic_payload["session_id"]
    assert dynamic_payload["ws_url"].endswith(f"/api/v1/teacher/qr/sessions/{dynamic_payload['session_id']}/stream")
    assert dynamic_payload["session_expires_at"]


@pytest.mark.asyncio
async def test_teacher_endpoints_require_teacher_role(session, api_client):
    role_admin = Role(code=RoleCode.ADMIN, name="Admin")
    admin = User(username="admin_api", full_name="Admin API", password_hash="x", must_change_password=False)
    admin.roles.append(role_admin)
    session.add_all([role_admin, admin])
    await session.commit()

    override_user(admin)
    response = await api_client.get("/api/v1/teacher/groups")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_teacher_lesson_attendance_returns_roster_and_hides_foreign_lessons(session, api_client):
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    teacher = User(username="teacher_owner", full_name="Teacher Owner", password_hash="x", must_change_password=False)
    teacher.roles.append(role_teacher)
    other_teacher = User(username="teacher_other", full_name="Teacher Other", password_hash="x", must_change_password=False)
    other_teacher.roles.append(role_teacher)
    student = User(username="student_api", full_name="Student API", password_hash="x", must_change_password=False)
    student.roles.append(role_student)

    group = Group(code="TG-2", name="Backend Group")
    discipline = Discipline(code="TD-2", name="Backend")
    session.add_all([role_teacher, role_student, teacher, other_teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        room="A-102",
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
            group_id=group.id,
            start_date=(now - timedelta(days=1)).date(),
            end_date=None,
            is_primary=True,
        )
    )
    session.add(
        AttendanceRecord(
            lesson_id=lesson.id,
            student_id=student.id,
            status=AttendanceStatus.LATE,
            source=AttendanceSource.TEACHER_MANUAL,
            marked_at=lesson.starts_at + timedelta(minutes=10),
            marked_by=teacher.id,
            correction_reason="Опоздал, но присутствовал",
            is_excused=False,
        )
    )
    await session.commit()

    override_user(teacher)
    response = await api_client.get(f"/api/v1/teacher/lessons/{lesson.id}/attendance")
    assert response.status_code == 200
    payload = response.json()
    assert payload["lesson"]["group_name"] == "Backend Group"
    assert payload["lesson"]["discipline_name"] == "Backend"
    assert payload["students"][0]["full_name"] == "Student API"
    assert payload["students"][0]["status"] == "late"
    assert payload["students"][0]["source"] == "teacher_manual"
    assert payload["students"][0]["correction_reason"] == "Опоздал, но присутствовал"

    override_user(other_teacher)
    foreign_response = await api_client.get(f"/api/v1/teacher/lessons/{lesson.id}/attendance")
    assert foreign_response.status_code == 404


@pytest.mark.asyncio
async def test_teacher_absence_reasons_include_attachments_and_attachment_access_is_scoped(
    session,
    api_client,
    tmp_path,
):
    role_teacher = Role(code=RoleCode.TEACHER, name="Teacher")
    role_student = Role(code=RoleCode.STUDENT, name="Student")
    teacher = User(username="teacher_abs", full_name="Teacher Abs", password_hash="x", must_change_password=False)
    teacher.roles.append(role_teacher)
    other_teacher = User(
        username="teacher_abs_other",
        full_name="Teacher Abs Other",
        password_hash="x",
        must_change_password=False,
    )
    other_teacher.roles.append(role_teacher)
    student = User(username="student_abs", full_name="Student Abs", password_hash="x", must_change_password=False)
    student.roles.append(role_student)

    group = Group(code="TG-3", name="Algorithms")
    discipline = Discipline(code="TD-3", name="Algorithms")
    session.add_all([role_teacher, role_student, teacher, other_teacher, student, group, discipline])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        room="C-303",
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=20,
    )
    session.add(lesson)
    await session.flush()

    reason = AbsenceReason(
        lesson_id=lesson.id,
        student_id=student.id,
        reason_type=AbsenceReasonType.ILLNESS,
        comment="Справка приложена",
        is_predeclared=True,
        moderation_status=ModerationStatus.PENDING,
        moderation_comment="Ожидает проверки",
    )
    session.add(reason)
    await session.flush()

    file_path = tmp_path / "proof.pdf"
    file_path.write_bytes(b"proof-data")
    attachment = AbsenceAttachment(
        reason_id=reason.id,
        file_name="proof.pdf",
        file_path=str(file_path),
        content_type="application/pdf",
        size_bytes=10,
    )
    session.add(attachment)
    await session.commit()

    override_user(teacher)
    reasons_response = await api_client.get("/api/v1/teacher/absence-reasons")
    assert reasons_response.status_code == 200
    payload = reasons_response.json()
    assert payload[0]["student_name"] == "Student Abs"
    assert payload[0]["group_name"] == "Algorithms"
    assert payload[0]["moderation_comment"] == "Ожидает проверки"
    assert payload[0]["attachments"][0]["file_name"] == "proof.pdf"

    download_response = await api_client.get(f"/api/v1/teacher/absence-reasons/attachments/{attachment.id}")
    assert download_response.status_code == 200
    assert download_response.content == b"proof-data"

    override_user(other_teacher)
    forbidden_response = await api_client.get(f"/api/v1/teacher/absence-reasons/attachments/{attachment.id}")
    assert forbidden_response.status_code == 404
