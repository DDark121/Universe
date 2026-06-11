from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.db.enums import ExportFormat, ExportJobType, ImportJobType, RoleCode
from app.db.models import Discipline, ExportJob, Group, ImportJob, Lesson, Role, User
from app.services import import_export


@pytest.mark.asyncio
async def test_load_rows_async_supports_csv_and_xlsx(tmp_path: Path):
    csv_path = tmp_path / "users.csv"
    csv_path.write_text("username,roles\nstudent_csv,student\n", encoding="utf-8")

    csv_rows = await import_export.load_rows_async(str(csv_path))

    assert csv_rows == [{"username": "student_csv", "roles": "student"}]

    xlsx_path = tmp_path / "users.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["username", "roles"])
    worksheet.append(["student_xlsx", "student"])
    workbook.save(xlsx_path)

    xlsx_rows = await import_export.load_rows_async(str(xlsx_path))

    assert xlsx_rows == [{"username": "student_xlsx", "roles": "student"}]


@pytest.mark.asyncio
async def test_async_import_export_helpers_write_reports_and_exports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(import_export, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(import_export, "IMPORTS_DIR", tmp_path / "imports")
    monkeypatch.setattr(import_export, "IMPORT_ERRORS_DIR", tmp_path / "errors")

    job_id = uuid4()
    error_path = await import_export.write_error_report_async(job_id, [{"row": 2, "error": "bad row"}])

    assert Path(error_path).exists()
    assert Path(error_path).read_text(encoding="utf-8").splitlines() == ["row,error", "2,bad row"]

    export_path = await import_export.build_export_path_async(job_id, ExportFormat.CSV)
    await import_export.export_rows_async(export_path, ExportFormat.CSV, [{"id": "1", "name": "Ada"}])

    assert export_path.exists()
    assert export_path.read_text(encoding="utf-8").splitlines() == ["id,name", "1,Ada"]


@pytest.mark.asyncio
async def test_schedule_import_creates_missing_entities_and_schedule_export_returns_rows(session, tmp_path: Path):
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    teacher_role = Role(code=RoleCode.TEACHER, name="Teacher")
    admin = User(username="import_admin", full_name="Import Admin", password_hash="x", must_change_password=False)
    admin.roles.append(admin_role)
    session.add_all([admin_role, teacher_role, admin])
    await session.flush()

    schedule_path = tmp_path / "schedule.csv"
    schedule_path.write_text(
        "\n".join(
            [
                "group_code,group_name,discipline_name,teacher_name,date,start_time,end_time,room,status",
                "164.22,164.22,Web-разработка,Мария Иванова,2026-06-08,08:30,10:00,A-204,planned",
            ]
        ),
        encoding="utf-8",
    )
    job = ImportJob(
        created_by=admin.id,
        job_type=ImportJobType.SCHEDULE,
        file_name=schedule_path.name,
        file_path=str(schedule_path),
    )
    session.add(job)
    await session.commit()

    result = await import_export.process_import_schedule(session, job)

    assert result.total_rows == 1
    assert result.processed_rows == 1
    assert result.errors == []

    group = (await session.execute(select(Group).where(Group.code == "164.22"))).scalar_one()
    discipline = (
        await session.execute(select(Discipline).where(Discipline.name == "Web-разработка"))
    ).scalar_one()
    lesson = (
        await session.execute(
            select(Lesson).where(Lesson.group_id == group.id, Lesson.discipline_id == discipline.id)
        )
    ).scalar_one()
    assert lesson.room == "A-204"

    export_job = ExportJob(
        created_by=admin.id,
        job_type=ExportJobType.SCHEDULE,
        format=ExportFormat.CSV,
        filters={"group_code": "164.22"},
    )
    session.add(export_job)
    await session.flush()

    rows = await import_export.build_export_rows(session, export_job)

    assert rows == [
        {
            "lesson_id": str(lesson.id),
            "group_id": str(group.id),
            "group_code": "164.22",
            "group_name": "164.22",
            "discipline_id": str(discipline.id),
            "discipline_code": "WEB-РАЗРАБОТКА",
            "discipline_name": "Web-разработка",
            "teacher_id": rows[0]["teacher_id"],
            "teacher_username": rows[0]["teacher_username"],
            "teacher_name": "Мария Иванова",
            "starts_at": rows[0]["starts_at"],
            "ends_at": rows[0]["ends_at"],
            "date": "2026-06-08",
            "start_time": "08:30",
            "end_time": "10:00",
            "room": "A-204",
            "status": "planned",
        }
    ]
