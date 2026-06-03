from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from openpyxl import Workbook

from app.db.enums import ExportFormat
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
