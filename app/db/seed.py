from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.db.enums import (
    AbsenceReasonType,
    AttendanceSource,
    AttendanceStatus,
    LessonStatus,
    ModerationStatus,
    RoleCode,
)
from app.db.models import (
    AbsenceReason,
    AttendanceRecord,
    Discipline,
    EscalationRule,
    Faculty,
    Group,
    GroupTelegramChat,
    Lesson,
    LessonActivityScore,
    NotificationTemplate,
    RatingConfig,
    RatingSnapshot,
    RiskCard,
    Role,
    Stream,
    StudentGroupMembership,
    SystemSetting,
    TeacherAssignment,
    TelegramAccount,
    TutorGroupAssignment,
    User,
    UserRole,
)

DEFAULT_TEMPLATES = {
    "attendance_window_open": "Окно отметки открыто.",
    "attendance_window_close_soon": "Скоро закрытие окна отметки.",
    "attendance_late_detected": "Зафиксировано опоздание на занятие.",
    "absence_reason_requested": "Вы пропустили занятие. Укажите причину отсутствия.",
    "reason_moderation_result": "Результат модерации причины обновлен.",
    "lesson_rescheduled": "Занятие перенесено.",
    "lesson_canceled": "Занятие отменено.",
    "risk_warning": "Внимание: вы находитесь в зоне риска.",
    "tutor_risk_warning": "У студента вашей группы сработал риск-порог.",
    "tutor_broadcast": "Сообщение от тьютора.",
    "teacher_broadcast": "Сообщение от преподавателя.",
}


async def _ensure_roles(session):
    for role_code in RoleCode:
        stmt = select(Role).where(Role.code == role_code)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if not existing:
            display_name = "Тьютор" if role_code == RoleCode.CURATOR else role_code.value.capitalize()
            session.add(Role(code=role_code, name=display_name))


async def _ensure_admin(session):
    stmt = select(User).where(User.username == "admin")
    admin = (await session.execute(stmt)).scalar_one_or_none()
    if admin:
        return

    admin = User(
        username="admin",
        full_name="System Administrator",
        email="admin@example.local",
        phone_number="+70000000000",
        password_hash=hash_password("Admin123!"),
        must_change_password=True,
        is_active=True,
    )
    session.add(admin)
    await session.flush()

    role_stmt = select(Role).where(Role.code == RoleCode.ADMIN)
    admin_role = (await session.execute(role_stmt)).scalar_one()
    session.add(UserRole(user_id=admin.id, role_id=admin_role.id))


async def _ensure_templates(session):
    for code, body in DEFAULT_TEMPLATES.items():
        stmt = select(NotificationTemplate).where(NotificationTemplate.code == code)
        if (await session.execute(stmt)).scalar_one_or_none():
            continue
        session.add(NotificationTemplate(code=code, title=None, body=body, is_active=True))


async def _ensure_rating(session):
    stmt = select(RatingConfig).limit(1)
    if (await session.execute(stmt)).scalar_one_or_none():
        return
    session.add(
        RatingConfig(
            attendance_weight=Decimal("50.00"),
            late_weight=Decimal("20.00"),
            unexcused_absence_weight=Decimal("30.00"),
            activity_weight=Decimal("0.00"),
        )
    )


async def _ensure_escalation_rule(session):
    stmt = select(EscalationRule).where(EscalationRule.name == "default-moderate")
    if (await session.execute(stmt)).scalar_one_or_none():
        return

    session.add(
        EscalationRule(
            name="default-moderate",
            threshold_unexcused_absences=3,
            threshold_lates=4,
            min_rating=60,
            is_active=True,
        )
    )


async def _ensure_default_settings(session):
    defaults = {
        "attendance.default_window_start_offset_minutes": {"value": -5},
        "attendance.default_window_duration_minutes": {"value": 20},
        "attendance.default_late_threshold_minutes": {"value": 20},
        "attendance.button_enabled": {"value": True},
        "attendance.teacher_correction_window_days": {"value": 3},
        "attendance.qr_dynamic_slot_seconds": {"value": 3},
        "attendance.qr_dynamic_grace_slots": {"value": 2},
        "security.audit_retention_months": {"value": 24},
        "security.biometric.max_timestamp_drift_seconds": {"value": 30},
        "security.biometric.nonce_ttl_seconds": {"value": 90},
        "localization.language": {"value": "ru"},
        "auth.2fa.optional": {"value": True},
        "tutor.broadcast.max_message_len": {"value": 2000},
        "risk.notify_tutor": {"value": True},
    }
    for key, value in defaults.items():
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        if (await session.execute(stmt)).scalar_one_or_none():
            continue
        session.add(SystemSetting(key=key, value=value))


async def _role(session, code: RoleCode) -> Role:
    row = (await session.execute(select(Role).where(Role.code == code))).scalar_one()
    return row


async def _ensure_demo_user(
    session,
    *,
    username: str,
    full_name: str,
    roles: list[RoleCode],
    email: str,
    phone_number: str,
    telegram_id: int | None = None,
) -> User:
    user = (
        await session.execute(
            select(User).where(User.username == username).options(selectinload(User.roles))
        )
    ).scalar_one_or_none()
    if not user:
        user = User(
            username=username,
            full_name=full_name,
            email=email,
            phone_number=phone_number,
            password_hash=hash_password("Demo123!"),
            must_change_password=False,
            is_active=True,
        )
        session.add(user)
        await session.flush()

    user.full_name = full_name
    if user.email is None:
        user.email = email
    if user.phone_number is None:
        user.phone_number = phone_number

    existing_roles = {
        role.code
        for role in (
            await session.execute(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user.id)
            )
        ).scalars().all()
    }
    for role_code in roles:
        if role_code not in existing_roles:
            role = await _role(session, role_code)
            session.add(UserRole(user_id=user.id, role_id=role.id))
            existing_roles.add(role_code)

    if telegram_id is not None:
        account = (
            await session.execute(select(TelegramAccount).where(TelegramAccount.user_id == user.id))
        ).scalar_one_or_none()
        if account:
            account.telegram_id = telegram_id
            account.username = username
            account.first_name = full_name.split()[0]
            account.last_name = " ".join(full_name.split()[1:]) or None
        else:
            account = (
                await session.execute(select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id))
            ).scalar_one_or_none()
            if account:
                account.user_id = user.id
                account.username = username
            else:
                session.add(
                    TelegramAccount(
                        user_id=user.id,
                        telegram_id=telegram_id,
                        username=username,
                        first_name=full_name.split()[0],
                        last_name=" ".join(full_name.split()[1:]) or None,
                    )
                )

    return user


async def _ensure_demo_structure(session) -> tuple[Group, dict[str, Discipline]]:
    faculty = (await session.execute(select(Faculty).where(Faculty.code == "TGTU-IT"))).scalar_one_or_none()
    if not faculty:
        faculty = Faculty(code="TGTU-IT", name="Институт цифровых технологий")
        session.add(faculty)
        await session.flush()

    stream = (
        await session.execute(
            select(Stream).where(Stream.faculty_id == faculty.id, Stream.name == "Программная инженерия")
        )
    ).scalar_one_or_none()
    if not stream:
        stream = Stream(faculty_id=faculty.id, name="Программная инженерия")
        session.add(stream)
        await session.flush()

    group = (await session.execute(select(Group).where(Group.code == "164.22"))).scalar_one_or_none()
    if not group:
        group = Group(
            faculty_id=faculty.id,
            stream_id=stream.id,
            code="164.22",
            name="164.22",
        )
        session.add(group)
        await session.flush()
    else:
        group.faculty_id = faculty.id
        group.stream_id = stream.id
        group.name = "164.22"

    chat = (
        await session.execute(select(GroupTelegramChat).where(GroupTelegramChat.group_id == group.id))
    ).scalar_one_or_none()
    if chat:
        chat.telegram_chat_id = -100164220001
        chat.title = "164.22 учебный чат"
        chat.is_active = True
    else:
        session.add(
            GroupTelegramChat(
                group_id=group.id,
                telegram_chat_id=-100164220001,
                title="164.22 учебный чат",
                is_active=True,
            )
        )

    discipline_rows = {
        "PRG": "Программирование на Python",
        "DB": "Базы данных",
        "WEB": "Web-разработка",
        "MATH": "Дискретная математика",
        "ENG": "Английский язык",
        "OS": "Операционные системы",
        "SEC": "Информационная безопасность",
        "PM": "Проектная деятельность",
    }
    disciplines: dict[str, Discipline] = {}
    for code, name in discipline_rows.items():
        row = (await session.execute(select(Discipline).where(Discipline.code == code))).scalar_one_or_none()
        if not row:
            row = Discipline(code=code, name=name)
            session.add(row)
            await session.flush()
        else:
            row.name = name
        disciplines[code] = row

    return group, disciplines


async def _ensure_membership(session, *, student: User, group: Group) -> None:
    row = (
        await session.execute(
            select(StudentGroupMembership).where(
                StudentGroupMembership.student_id == student.id,
                StudentGroupMembership.group_id == group.id,
                StudentGroupMembership.end_date.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row:
        row.is_primary = True
        return
    session.add(
        StudentGroupMembership(
            student_id=student.id,
            group_id=group.id,
            start_date=date(2026, 5, 1),
            is_primary=True,
        )
    )


async def _ensure_teacher_assignment(session, *, teacher: User, discipline: Discipline, group: Group) -> None:
    row = (
        await session.execute(
            select(TeacherAssignment).where(
                TeacherAssignment.teacher_id == teacher.id,
                TeacherAssignment.discipline_id == discipline.id,
                TeacherAssignment.group_id == group.id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.is_active = True
        return
    session.add(
        TeacherAssignment(
            teacher_id=teacher.id,
            discipline_id=discipline.id,
            group_id=group.id,
            is_active=True,
        )
    )


async def _ensure_tutor_assignment(session, *, tutor: User, group: Group) -> None:
    row = (
        await session.execute(
            select(TutorGroupAssignment).where(
                TutorGroupAssignment.tutor_user_id == tutor.id,
                TutorGroupAssignment.group_id == group.id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.is_active = True
        return
    session.add(TutorGroupAssignment(tutor_user_id=tutor.id, group_id=group.id, is_active=True))


def _lesson_dt(day: date, starts: time) -> datetime:
    return datetime.combine(day, starts, tzinfo=UTC)


async def _ensure_lesson(
    session,
    *,
    group: Group,
    discipline: Discipline,
    teacher: User,
    day: date,
    starts: time,
    ends: time,
    room: str,
    status: LessonStatus,
) -> Lesson:
    starts_at = _lesson_dt(day, starts)
    row = (
        await session.execute(
            select(Lesson).where(
                Lesson.group_id == group.id,
                Lesson.discipline_id == discipline.id,
                Lesson.teacher_id == teacher.id,
                Lesson.starts_at == starts_at,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.ends_at = _lesson_dt(day, ends)
        row.room = room
        row.status = status
        return row

    row = Lesson(
        group_id=group.id,
        discipline_id=discipline.id,
        teacher_id=teacher.id,
        starts_at=starts_at,
        ends_at=_lesson_dt(day, ends),
        room=room,
        status=status,
        window_start_offset_minutes=-5,
        window_duration_minutes=20,
        late_threshold_minutes=15,
    )
    session.add(row)
    await session.flush()
    return row


async def _ensure_attendance(
    session,
    *,
    lesson: Lesson,
    student: User,
    status_value: AttendanceStatus,
    marked_at: datetime,
    is_excused: bool,
    excused_category: str | None,
) -> AttendanceRecord:
    row = (
        await session.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.lesson_id == lesson.id,
                AttendanceRecord.student_id == student.id,
            )
        )
    ).scalar_one_or_none()
    source = AttendanceSource.AUTO_ABSENCE if status_value == AttendanceStatus.ABSENT else AttendanceSource.TEACHER_MANUAL
    if row:
        row.status = status_value
        row.source = source
        row.marked_at = marked_at
        row.marked_by = lesson.teacher_id
        row.is_excused = is_excused
        row.excused_category = excused_category
        return row

    row = AttendanceRecord(
        lesson_id=lesson.id,
        student_id=student.id,
        status=status_value,
        source=source,
        marked_at=marked_at,
        marked_by=lesson.teacher_id,
        is_excused=is_excused,
        excused_category=excused_category,
    )
    session.add(row)
    await session.flush()
    return row


async def _ensure_absence_reason(session, *, record: AttendanceRecord, accepted: bool) -> None:
    row = (
        await session.execute(
            select(AbsenceReason).where(
                AbsenceReason.lesson_id == record.lesson_id,
                AbsenceReason.student_id == record.student_id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.reason_type = AbsenceReasonType.ILLNESS if record.is_excused else AbsenceReasonType.OTHER
        row.moderation_status = ModerationStatus.ACCEPTED if accepted else ModerationStatus.REJECTED
        row.comment = "Демо-причина отсутствия за месяц"
        return
    session.add(
        AbsenceReason(
            lesson_id=record.lesson_id,
            student_id=record.student_id,
            reason_type=AbsenceReasonType.ILLNESS if record.is_excused else AbsenceReasonType.OTHER,
            comment="Демо-причина отсутствия за месяц",
            is_predeclared=record.is_excused,
            moderation_status=ModerationStatus.ACCEPTED if accepted else ModerationStatus.REJECTED,
            moderated_by=record.marked_by,
            moderation_comment="Демо-модерация",
            moderated_at=record.marked_at + timedelta(hours=2),
        )
    )


async def _ensure_activity_score(session, *, lesson: Lesson, student: User, score: float) -> None:
    row = (
        await session.execute(
            select(LessonActivityScore).where(
                LessonActivityScore.lesson_id == lesson.id,
                LessonActivityScore.student_id == student.id,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.score = score
        row.comment = "Демо-активность на паре"
        row.recorded_by = lesson.teacher_id
        return
    session.add(
        LessonActivityScore(
            lesson_id=lesson.id,
            student_id=student.id,
            score=score,
            comment="Демо-активность на паре",
            recorded_by=lesson.teacher_id,
        )
    )


async def _ensure_rating_snapshot(
    session,
    *,
    student: User,
    group: Group,
    period_start: date,
    period_end: date,
    total: int,
    present: int,
    late: int,
    unexcused: int,
) -> RatingSnapshot:
    attendance_pct = round(((present + late) / total * 100) if total else 0, 2)
    score = round(
        max(
            0,
            min(
                100,
                attendance_pct * 0.5
                + max(0, 100 - late * 10) * 0.2
                + max(0, 100 - unexcused * 25) * 0.3,
            ),
        ),
        2,
    )
    row = (
        await session.execute(
            select(RatingSnapshot).where(
                RatingSnapshot.student_id == student.id,
                RatingSnapshot.group_id == group.id,
                RatingSnapshot.period_start == period_start,
                RatingSnapshot.period_end == period_end,
            )
        )
    ).scalar_one_or_none()
    if row:
        row.attendance_pct = attendance_pct
        row.late_count = late
        row.unexcused_absence_count = unexcused
        row.score = score
    else:
        row = RatingSnapshot(
            student_id=student.id,
            group_id=group.id,
            period_start=period_start,
            period_end=period_end,
            attendance_pct=attendance_pct,
            late_count=late,
            unexcused_absence_count=unexcused,
            score=score,
        )
        session.add(row)
        await session.flush()

    if late >= 4 or unexcused >= 3 or score < 60:
        risk = (
            await session.execute(
                select(RiskCard).where(RiskCard.student_id == student.id, RiskCard.is_active.is_(True))
            )
        ).scalar_one_or_none()
        reasons = {
            "demo": True,
            "score": score,
            "late_count": late,
            "unexcused_absence_count": unexcused,
        }
        if risk:
            risk.last_score = score
            risk.late_count = late
            risk.unexcused_absence_count = unexcused
            risk.reasons = reasons
        else:
            session.add(
                RiskCard(
                    student_id=student.id,
                    is_active=True,
                    last_score=score,
                    late_count=late,
                    unexcused_absence_count=unexcused,
                    reasons=reasons,
                )
            )
    return row


async def _ensure_demo_group_16422(session) -> None:
    group, disciplines = await _ensure_demo_structure(session)

    tutor = await _ensure_demo_user(
        session,
        username="tutor_16422",
        full_name="Алина Сергеевна Тьютор",
        roles=[RoleCode.CURATOR],
        email="tutor.16422@example.local",
        phone_number="+77001642200",
        telegram_id=164220000,
    )
    await _ensure_tutor_assignment(session, tutor=tutor, group=group)

    teachers = {
        "PRG": await _ensure_demo_user(
            session,
            username="teacher_python",
            full_name="Игорь Павлович Соколов",
            roles=[RoleCode.TEACHER],
            email="teacher.python@example.local",
            phone_number="+77001642210",
            telegram_id=164220010,
        ),
        "DB": await _ensure_demo_user(
            session,
            username="teacher_db",
            full_name="Мария Андреевна Ким",
            roles=[RoleCode.TEACHER],
            email="teacher.db@example.local",
            phone_number="+77001642211",
            telegram_id=164220011,
        ),
        "WEB": await _ensure_demo_user(
            session,
            username="teacher_web",
            full_name="Руслан Тимурович Галиев",
            roles=[RoleCode.TEACHER],
            email="teacher.web@example.local",
            phone_number="+77001642212",
            telegram_id=164220012,
        ),
        "MATH": await _ensure_demo_user(
            session,
            username="teacher_math",
            full_name="Елена Викторовна Орлова",
            roles=[RoleCode.TEACHER],
            email="teacher.math@example.local",
            phone_number="+77001642213",
            telegram_id=164220013,
        ),
        "ENG": await _ensure_demo_user(
            session,
            username="teacher_english",
            full_name="Данияр Муратович Ахметов",
            roles=[RoleCode.TEACHER],
            email="teacher.english@example.local",
            phone_number="+77001642214",
            telegram_id=164220014,
        ),
        "OS": await _ensure_demo_user(
            session,
            username="teacher_os",
            full_name="Наталья Игоревна Белова",
            roles=[RoleCode.TEACHER],
            email="teacher.os@example.local",
            phone_number="+77001642215",
        ),
        "SEC": await _ensure_demo_user(
            session,
            username="teacher_security",
            full_name="Арман Ерланович Нурпеисов",
            roles=[RoleCode.TEACHER],
            email="teacher.security@example.local",
            phone_number="+77001642216",
        ),
        "PM": await _ensure_demo_user(
            session,
            username="teacher_project",
            full_name="Светлана Олеговна Морозова",
            roles=[RoleCode.TEACHER],
            email="teacher.project@example.local",
            phone_number="+77001642217",
        ),
    }
    for discipline_code, teacher in teachers.items():
        await _ensure_teacher_assignment(
            session,
            teacher=teacher,
            discipline=disciplines[discipline_code],
            group=group,
        )

    student_names = [
        ("student_16422_01", "Алишер Кайратов"),
        ("student_16422_02", "Виктория Романова"),
        ("student_16422_03", "Дамир Сулейменов"),
        ("student_16422_04", "Екатерина Ли"),
        ("student_16422_05", "Илья Ковалев"),
        ("student_16422_06", "Мадина Оспанова"),
        ("student_16422_07", "Никита Федоров"),
        ("student_16422_08", "София Чернова"),
    ]
    students: list[User] = []
    for index, (username, full_name) in enumerate(student_names, start=1):
        student = await _ensure_demo_user(
            session,
            username=username,
            full_name=full_name,
            roles=[RoleCode.STUDENT],
            email=f"{username}@example.local",
            phone_number=f"+770016422{20 + index:02d}",
            telegram_id=164220100 + index,
        )
        await _ensure_membership(session, student=student, group=group)
        students.append(student)

    weekly_pairs = [
        (0, time(8, 30), time(10, 0), "PRG", "A-204"),
        (0, time(10, 10), time(11, 40), "MATH", "B-115"),
        (0, time(12, 10), time(13, 40), "ENG", "L-302"),
        (1, time(8, 30), time(10, 0), "DB", "A-301"),
        (1, time(10, 10), time(11, 40), "WEB", "C-210"),
        (1, time(12, 10), time(13, 40), "PM", "Coworking-1"),
        (2, time(8, 30), time(10, 0), "OS", "B-207"),
        (2, time(10, 10), time(11, 40), "PRG", "A-204"),
        (2, time(12, 10), time(13, 40), "SEC", "C-104"),
        (3, time(8, 30), time(10, 0), "DB", "A-301"),
        (3, time(10, 10), time(11, 40), "MATH", "B-115"),
        (3, time(12, 10), time(13, 40), "WEB", "C-210"),
        (4, time(8, 30), time(10, 0), "ENG", "L-302"),
        (4, time(10, 10), time(11, 40), "OS", "B-207"),
        (4, time(12, 10), time(13, 40), "PM", "Coworking-1"),
    ]
    week_starts = [date(2026, 5, 4), date(2026, 5, 11), date(2026, 5, 18), date(2026, 5, 25), date(2026, 6, 8)]
    monthly_stats = {student.id: {"total": 0, "present": 0, "late": 0, "unexcused": 0} for student in students}
    lesson_index = 0

    for week_start in week_starts:
        is_history_week = week_start.month == 5
        for day_offset, starts, ends, discipline_code, room in weekly_pairs:
            lesson_day = week_start + timedelta(days=day_offset)
            lesson = await _ensure_lesson(
                session,
                group=group,
                discipline=disciplines[discipline_code],
                teacher=teachers[discipline_code],
                day=lesson_day,
                starts=starts,
                ends=ends,
                room=room,
                status=LessonStatus.COMPLETED if is_history_week else LessonStatus.PLANNED,
            )
            if not is_history_week:
                continue

            for student_index, student in enumerate(students, start=1):
                selector = (lesson_index + student_index) % 13
                if selector == 0:
                    status_value = AttendanceStatus.ABSENT
                    is_excused = False
                    excused_category = None
                    marked_at = lesson.ends_at
                elif selector in {5, 11}:
                    status_value = AttendanceStatus.ABSENT
                    is_excused = True
                    excused_category = "illness"
                    marked_at = lesson.ends_at
                elif selector in {3, 8}:
                    status_value = AttendanceStatus.LATE
                    is_excused = False
                    excused_category = None
                    marked_at = lesson.starts_at + timedelta(minutes=22)
                else:
                    status_value = AttendanceStatus.PRESENT
                    is_excused = False
                    excused_category = None
                    marked_at = lesson.starts_at + timedelta(minutes=4)

                record = await _ensure_attendance(
                    session,
                    lesson=lesson,
                    student=student,
                    status_value=status_value,
                    marked_at=marked_at,
                    is_excused=is_excused,
                    excused_category=excused_category,
                )
                stats = monthly_stats[student.id]
                stats["total"] += 1
                if status_value == AttendanceStatus.PRESENT:
                    stats["present"] += 1
                elif status_value == AttendanceStatus.LATE:
                    stats["late"] += 1
                elif not is_excused:
                    stats["unexcused"] += 1

                if status_value == AttendanceStatus.ABSENT:
                    await _ensure_absence_reason(session, record=record, accepted=is_excused)
                elif lesson_index % 4 == 0:
                    await _ensure_activity_score(
                        session,
                        lesson=lesson,
                        student=student,
                        score=4.0 if status_value == AttendanceStatus.PRESENT else 3.0,
                    )

            lesson_index += 1

    for student in students:
        stats = monthly_stats[student.id]
        await _ensure_rating_snapshot(
            session,
            student=student,
            group=group,
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            total=stats["total"],
            present=stats["present"],
            late=stats["late"],
            unexcused=stats["unexcused"],
        )


async def seed_initial_data() -> None:
    async with SessionLocal() as session:
        try:
            await _ensure_roles(session)
            await _ensure_admin(session)
            await _ensure_templates(session)
            await _ensure_rating(session)
            await _ensure_escalation_rule(session)
            await _ensure_default_settings(session)
            await _ensure_demo_group_16422(session)
            await session.commit()
        except (SQLAlchemyError, OSError):
            # Migrations, database DNS, or the database itself might still be settling on container boot.
            await session.rollback()


if __name__ == "__main__":
    asyncio.run(seed_initial_data())
