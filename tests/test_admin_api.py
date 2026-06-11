from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.core.db import get_db_session
from app.core.security import hash_password
from app.core.time import utc_now
from app.db.enums import AttendanceSource, AttendanceStatus, LessonStatus, RoleCode
from app.db.models import (
    AttendanceRecord,
    Discipline,
    Faculty,
    Group,
    GroupTelegramChat,
    Lesson,
    NotificationOutbox,
    RiskCard,
    Role,
    StudentGroupMembership,
    TelegramAccount,
    TutorGroupAssignment,
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


async def login_headers(api_client: AsyncClient, username: str, password: str) -> dict[str, str]:
    response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_admin_can_create_teacher_without_missing_greenlet(session, api_client):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    admin = User(username="admin_api", full_name="Admin API", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    session.add_all([admin_role, teacher_role, admin])
    await session.commit()

    override_user(admin)

    response = await api_client.post(
        "/api/v1/admin/users",
        json={
            "username": "teacher_new",
            "full_name": "Teacher New",
            "email": "teacher@example.local",
            "phone_number": "+77010000001",
            "roles": ["teacher"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "teacher_new"
    assert payload["phone_number"] == "+77010000001"
    assert payload["roles"] == ["teacher"]
    assert payload["temp_password"]

    created = (
        await session.execute(select(User).where(User.username == "teacher_new").options(selectinload(User.roles)))
    ).scalar_one()
    assert created.must_change_password is True
    assert created.phone_number == "+77010000001"
    assert {role.code for role in created.roles} == {RoleCode.TEACHER}


@pytest.mark.asyncio
async def test_admin_bootstrap_flow_creates_group_contacts_and_schedule_via_api(session, api_client):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    curator_role = Role(code=RoleCode.CURATOR, name="Curator")
    admin = User(
        username="admin_flow",
        full_name="Admin Flow",
        email="admin.flow@example.local",
        phone_number="+77010000010",
        password_hash=hash_password("AdminFlow123!"),
        must_change_password=False,
    )
    admin.roles.append(admin_role)
    session.add_all([admin_role, student_role, teacher_role, curator_role, admin])
    await session.commit()

    headers = await login_headers(api_client, "admin_flow", "AdminFlow123!")

    faculty_response = await api_client.post(
        "/api/v1/admin/faculties",
        json={"code": "FIT-API", "name": "Faculty API"},
        headers=headers,
    )
    assert faculty_response.status_code == 200
    faculty_id = faculty_response.json()["id"]

    stream_response = await api_client.post(
        "/api/v1/admin/streams",
        json={"faculty_id": faculty_id, "name": "SE Stream API"},
        headers=headers,
    )
    assert stream_response.status_code == 200
    stream_id = stream_response.json()["id"]

    group_response = await api_client.post(
        "/api/v1/admin/groups",
        json={
            "code": "SE-API-101",
            "name": "SE API 101",
            "faculty_id": faculty_id,
            "stream_id": stream_id,
        },
        headers=headers,
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]

    discipline_response = await api_client.post(
        "/api/v1/admin/disciplines",
        json={"code": "DB-API", "name": "Databases API"},
        headers=headers,
    )
    assert discipline_response.status_code == 200
    discipline_id = discipline_response.json()["id"]

    tutor_response = await api_client.post(
        "/api/v1/admin/users",
        json={
            "username": "tutor_api_flow",
            "full_name": "Tutor API Flow",
            "email": "tutor.api@example.local",
            "phone_number": "+77010000011",
            "roles": ["curator"],
        },
        headers=headers,
    )
    assert tutor_response.status_code == 200
    tutor_payload = tutor_response.json()

    teacher_response = await api_client.post(
        "/api/v1/admin/users",
        json={
            "username": "teacher_api_flow",
            "full_name": "Teacher API Flow",
            "email": "teacher.api@example.local",
            "phone_number": "+77010000012",
            "roles": ["teacher"],
        },
        headers=headers,
    )
    assert teacher_response.status_code == 200
    teacher_payload = teacher_response.json()

    student_response = await api_client.post(
        "/api/v1/admin/users",
        json={
            "username": "student_api_flow",
            "full_name": "Student API Flow",
            "email": "student.api@example.local",
            "phone_number": "+77010000013",
            "roles": ["student"],
        },
        headers=headers,
    )
    assert student_response.status_code == 200
    student_payload = student_response.json()

    tutor_assignment_response = await api_client.post(
        "/api/v1/admin/tutor-assignments",
        json={"tutor_user_id": tutor_payload["id"], "group_id": group_id},
        headers=headers,
    )
    assert tutor_assignment_response.status_code == 200

    teacher_assignment_response = await api_client.post(
        "/api/v1/admin/assignments",
        json={
            "teacher_id": teacher_payload["id"],
            "discipline_id": discipline_id,
            "group_id": group_id,
        },
        headers=headers,
    )
    assert teacher_assignment_response.status_code == 200

    transfer_response = await api_client.post(
        "/api/v1/admin/student-transfer",
        json={
            "student_id": student_payload["id"],
            "target_group_id": group_id,
            "transfer_date": utc_now().date().isoformat(),
        },
        headers=headers,
    )
    assert transfer_response.status_code == 200

    first_lesson_starts_at = utc_now().replace(microsecond=0) + timedelta(days=1)
    second_lesson_starts_at = first_lesson_starts_at + timedelta(days=2)

    for starts_at, room in ((first_lesson_starts_at, "A-101"), (second_lesson_starts_at, "A-103")):
        lesson_response = await api_client.post(
            "/api/v1/admin/lessons",
            json={
                "group_id": group_id,
                "discipline_id": discipline_id,
                "teacher_id": teacher_payload["id"],
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(hours=1, minutes=30)).isoformat(),
                "room": room,
            },
            headers=headers,
        )
        assert lesson_response.status_code == 200

    users_in_group = await api_client.get(
        "/api/v1/admin/users",
        params={"group_id": group_id, "search": "+77010000013"},
        headers=headers,
    )
    assert users_in_group.status_code == 200
    assert users_in_group.json()["meta"]["total"] == 1
    assert users_in_group.json()["items"][0]["phone_number"] == "+77010000013"

    tutor_headers = await login_headers(api_client, "tutor_api_flow", tutor_payload["temp_password"])
    tutor_groups = await api_client.get("/api/v1/admin/tutor/groups", headers=tutor_headers)
    assert tutor_groups.status_code == 200
    assert tutor_groups.json() == [{"id": group_id, "code": "SE-API-101", "name": "SE API 101"}]

    teacher_headers = await login_headers(api_client, "teacher_api_flow", teacher_payload["temp_password"])
    teacher_groups = await api_client.get("/api/v1/teacher/groups", headers=teacher_headers)
    assert teacher_groups.status_code == 200
    assert teacher_groups.json() == [{"id": group_id, "code": "SE-API-101", "name": "SE API 101"}]

    teacher_lessons = await api_client.get("/api/v1/teacher/lessons", headers=teacher_headers)
    assert teacher_lessons.status_code == 200
    assert len(teacher_lessons.json()) == 2

    student_headers = await login_headers(api_client, "student_api_flow", student_payload["temp_password"])
    me_response = await api_client.get("/api/v1/auth/me", headers=student_headers)
    assert me_response.status_code == 200
    assert me_response.json()["phone_number"] == "+77010000013"

    profile_response = await api_client.get("/api/v1/student/profile", headers=student_headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["phone_number"] == "+77010000013"

    schedule_response = await api_client.get("/api/v1/student/schedule", headers=student_headers)
    assert schedule_response.status_code == 200
    assert len(schedule_response.json()) == 2
    assert {item["room"] for item in schedule_response.json()} == {"A-101", "A-103"}


@pytest.mark.asyncio
async def test_admin_faq_endpoints_are_read_only_and_markdown_backed(session, api_client, faq_storage):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    admin = User(username="faq_admin", full_name="FAQ Admin", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    session.add_all([admin_role, admin])
    await session.commit()

    faq_path = faq_storage["source_dir"] / "general" / "telegram-binding.md"
    faq_path.parent.mkdir(parents=True, exist_ok=True)
    faq_path.write_text("Откройте mini app и отправьте заявку на привязку.", encoding="utf-8")

    override_user(admin)

    categories = await api_client.get("/api/v1/admin/faq/categories")
    assert categories.status_code == 200
    assert categories.json()["items"][0]["name"] == "general"

    items = await api_client.get("/api/v1/admin/faq/items", params={"query": "telegram"})
    assert items.status_code == 200
    assert items.json()["items"][0]["question"] == "telegram-binding"

    status_response = await api_client.get("/api/v1/admin/faq/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "missing"

    create_category = await api_client.post(
        "/api/v1/admin/faq/categories",
        json={"name": "New Category", "sort_order": 100},
    )
    assert create_category.status_code == 410

    create_item = await api_client.post(
        "/api/v1/admin/faq/items",
        json={
            "category_id": categories.json()["items"][0]["id"],
            "question": "new-item",
            "answer": "answer",
            "keywords": "",
        },
    )
    assert create_item.status_code == 410


@pytest.mark.asyncio
async def test_tutor_broadcast_queues_student_and_group_chat_notifications(session, api_client):
    curator_role = Role(code=RoleCode.CURATOR, name="Curator")
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    tutor = User(username="tutor_broadcast", full_name="Tutor Broadcast", password_hash="x", must_change_password=False)
    student_one = User(username="broadcast_s1", full_name="Broadcast Student 1", password_hash="x", must_change_password=False)
    student_two = User(username="broadcast_s2", full_name="Broadcast Student 2", password_hash="x", must_change_password=False)
    tutor.roles.append(curator_role)
    student_one.roles.append(student_role)
    student_two.roles.append(student_role)
    group = Group(code="TB-101", name="Tutor Broadcast 101")
    session.add_all([curator_role, student_role, tutor, student_one, student_two, group])
    await session.flush()
    session.add_all(
        [
            TutorGroupAssignment(tutor_user_id=tutor.id, group_id=group.id, is_active=True),
            StudentGroupMembership(
                student_id=student_one.id,
                group_id=group.id,
                start_date=utc_now().date(),
                is_primary=True,
            ),
            StudentGroupMembership(
                student_id=student_two.id,
                group_id=group.id,
                start_date=utc_now().date(),
                is_primary=True,
            ),
            TelegramAccount(user_id=student_one.id, telegram_id=700101, username="broadcast_s1"),
            TelegramAccount(user_id=student_two.id, telegram_id=700102, username="broadcast_s2"),
            GroupTelegramChat(group_id=group.id, telegram_chat_id=-100700101, title="TB-101 chat"),
        ]
    )
    await session.commit()

    override_user(tutor)

    response = await api_client.post(
        "/api/v1/admin/tutor/broadcasts",
        json={"group_id": str(group.id), "message": "Проверьте расписание на неделю"},
    )

    assert response.status_code == 200
    assert response.json()["recipients"] == 2
    assert response.json()["group_chat_queued"] is True

    outbox_rows = (
        await session.execute(
            select(NotificationOutbox).where(NotificationOutbox.event_type == "tutor_broadcast")
        )
    ).scalars().all()
    assert len(outbox_rows) == 3
    assert any(row.recipient_telegram_id == -100700101 and row.payload["delivery"] == "group_chat" for row in outbox_rows)


@pytest.mark.asyncio
async def test_admin_panel_assistant_endpoint_uses_llm_reply_for_admin_and_curator(session, api_client, monkeypatch):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    curator_role = Role(code=RoleCode.CURATOR, name="Curator")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    admin = User(username="assistant_admin", full_name="Assistant Admin", password_hash="x", must_change_password=False)
    curator = User(username="assistant_curator", full_name="Assistant Curator", password_hash="x", must_change_password=False)
    teacher = User(username="assistant_teacher", full_name="Assistant Teacher", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    curator.roles.append(curator_role)
    teacher.roles.append(teacher_role)
    session.add_all([admin_role, curator_role, teacher_role, admin, curator, teacher])
    await session.commit()

    llm_calls = []

    async def fake_panel_llm_reply(**kwargs):
        llm_calls.append(kwargs)
        return "Откройте раздел «Рассылки тьютора» и выберите группу."

    monkeypatch.setattr("app.services.faq_ai._generate_panel_llm_reply", fake_panel_llm_reply)

    override_user(curator)
    response = await api_client.post(
        "/api/v1/admin/assistant/reply",
        json={
            "message": "Как отправить рассылку?",
            "current_path": "/tutor/pushes",
            "history": [{"role": "user", "content": "Где отчеты?"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "llm"
    assert "Рассылки тьютора" in response.json()["message"]
    assert llm_calls[-1]["ctx"].current_path == "/tutor/pushes"
    assert llm_calls[-1]["history"] == [{"role": "user", "content": "Где отчеты?"}]

    override_user(admin)
    admin_response = await api_client.post(
        "/api/v1/admin/assistant/reply",
        json={"message": "Где импорт расписания?"},
    )
    assert admin_response.status_code == 200
    assert llm_calls[-1]["ctx"].roles == ["admin"]

    override_user(teacher)
    forbidden = await api_client.post(
        "/api/v1/admin/assistant/reply",
        json={"message": "Можно спросить?"},
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_endpoints_accept_page_size_500(session, api_client):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    admin = User(username="admin_lists", full_name="Admin Lists", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    group = Group(code="GR-500", name="Group 500")
    session.add_all([admin_role, admin, group])
    await session.commit()

    override_user(admin)

    users_response = await api_client.get("/api/v1/admin/users", params={"page_size": 500})
    groups_response = await api_client.get("/api/v1/admin/groups", params={"page_size": 500})
    audit_response = await api_client.get("/api/v1/admin/audit/logs", params={"page_size": 500})

    assert users_response.status_code == 200
    assert users_response.json()["meta"]["page_size"] == 500
    assert any(item["username"] == "admin_lists" for item in users_response.json()["items"])

    assert groups_response.status_code == 200
    assert groups_response.json()["meta"]["page_size"] == 500
    assert any(item["code"] == "GR-500" for item in groups_response.json()["items"])

    assert audit_response.status_code == 200
    assert audit_response.json()["meta"]["page_size"] == 500


@pytest.mark.asyncio
async def test_admin_risk_students_handles_json_reasons_without_duplicates(session, api_client):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    admin = User(username="risk_admin", full_name="Risk Admin", password_hash="x", must_change_password=False)
    student = User(username="risk_student", full_name="Risk Student", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    student.roles.append(student_role)

    faculty = Faculty(code="FIT", name="Faculty of IT")
    discipline = Discipline(code="DB", name="Databases")

    session.add_all([admin_role, student_role, admin, student, faculty, discipline])
    await session.flush()

    primary_group = Group(code="SE-301", name="SE-301", faculty_id=faculty.id)
    secondary_group = Group(code="SE-302", name="SE-302", faculty_id=faculty.id)
    session.add_all([primary_group, secondary_group])
    await session.flush()

    now = utc_now()
    lesson = Lesson(
        group_id=primary_group.id,
        discipline_id=discipline.id,
        teacher_id=admin.id,
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        room="A-301",
        status=LessonStatus.PLANNED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=10,
    )
    session.add(lesson)
    await session.flush()
    session.add_all(
        [
            StudentGroupMembership(
                student_id=student.id,
                group_id=primary_group.id,
                start_date=now.date(),
                is_primary=True,
            ),
            StudentGroupMembership(
                student_id=student.id,
                group_id=secondary_group.id,
                start_date=now.date(),
                is_primary=False,
            ),
            AttendanceRecord(
                lesson_id=lesson.id,
                student_id=student.id,
                status=AttendanceStatus.LATE,
                source=AttendanceSource.TEACHER_MANUAL,
                marked_at=now,
            ),
            RiskCard(
                student_id=student.id,
                is_active=True,
                last_score=42.5,
                unexcused_absence_count=2,
                late_count=3,
                reasons={"attendance": {"lates": 3}},
            ),
        ]
    )
    await session.commit()

    override_user(admin)

    response = await api_client.get(
        "/api/v1/admin/risk/students",
        params={"faculty_id": str(faculty.id), "discipline_id": str(discipline.id)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["total"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["student_id"] == str(student.id)
    assert payload["items"][0]["reasons"] == {"attendance": {"lates": 3}}


@pytest.mark.asyncio
async def test_students_analytics_ranks_best_and_worst_students_for_admin_and_curator(session, api_client):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    curator_role = Role(code=RoleCode.CURATOR, name="Curator")
    student_role = Role(code=RoleCode.STUDENT, name="Student")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    admin = User(username="student_analytics_admin", full_name="Student Analytics Admin", password_hash="x", must_change_password=False)
    curator = User(
        username="student_analytics_curator",
        full_name="Student Analytics Curator",
        password_hash="x",
        must_change_password=False,
    )
    teacher = User(username="student_analytics_teacher", full_name="Student Analytics Teacher", password_hash="x", must_change_password=False)
    good_student = User(username="student_analytics_good", full_name="Good Student", password_hash="x", must_change_password=False)
    bad_student = User(username="student_analytics_bad", full_name="Bad Student", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    curator.roles.append(curator_role)
    teacher.roles.append(teacher_role)
    good_student.roles.append(student_role)
    bad_student.roles.append(student_role)

    group = Group(code="AN-1", name="Analytics Group")
    foreign_group = Group(code="AN-2", name="Foreign Analytics Group")
    discipline = Discipline(code="AN-DB", name="Analytics Databases")
    session.add_all(
        [
            admin_role,
            curator_role,
            student_role,
            teacher_role,
            admin,
            curator,
            teacher,
            good_student,
            bad_student,
            group,
            foreign_group,
            discipline,
        ]
    )
    await session.flush()

    now = utc_now()
    lesson_one = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now,
        ends_at=now + timedelta(hours=1),
        room="A-401",
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=10,
    )
    lesson_two = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=3),
        room="A-402",
        status=LessonStatus.COMPLETED,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=10,
    )
    session.add_all([lesson_one, lesson_two])
    await session.flush()

    session.add_all(
        [
            TutorGroupAssignment(tutor_user_id=curator.id, group_id=group.id, is_active=True),
            StudentGroupMembership(student_id=good_student.id, group_id=group.id, start_date=now.date(), is_primary=True),
            StudentGroupMembership(student_id=bad_student.id, group_id=group.id, start_date=now.date(), is_primary=True),
            AttendanceRecord(
                lesson_id=lesson_one.id,
                student_id=good_student.id,
                status=AttendanceStatus.PRESENT,
                source=AttendanceSource.QR,
                marked_at=now,
            ),
            AttendanceRecord(
                lesson_id=lesson_two.id,
                student_id=good_student.id,
                status=AttendanceStatus.PRESENT,
                source=AttendanceSource.QR,
                marked_at=now,
            ),
            AttendanceRecord(
                lesson_id=lesson_one.id,
                student_id=bad_student.id,
                status=AttendanceStatus.ABSENT,
                source=AttendanceSource.AUTO_ABSENCE,
                marked_at=now,
                is_excused=False,
            ),
            AttendanceRecord(
                lesson_id=lesson_two.id,
                student_id=bad_student.id,
                status=AttendanceStatus.LATE,
                source=AttendanceSource.QR,
                marked_at=now,
            ),
        ]
    )
    await session.commit()

    override_user(admin)
    response = await api_client.get(
        "/api/v1/admin/analytics/students",
        params={"date_from": str(now.date()), "date_to": str(now.date()), "limit": "2"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_students"] == 2
    assert payload["total_marks"] == 4
    assert payload["best"][0]["student_id"] == str(good_student.id)
    assert payload["worst"][0]["student_id"] == str(bad_student.id)
    assert payload["worst"][0]["status"] in {"watch", "critical"}

    override_user(curator)
    curator_response = await api_client.get(
        "/api/v1/admin/analytics/students",
        params={"date_from": str(now.date()), "date_to": str(now.date()), "group_id": str(group.id)},
    )
    assert curator_response.status_code == 200
    assert curator_response.json()["total_students"] == 2

    forbidden = await api_client.get(
        "/api/v1/admin/analytics/students",
        params={"date_from": str(now.date()), "date_to": str(now.date()), "group_id": str(foreign_group.id)},
    )
    assert forbidden.status_code == 403
