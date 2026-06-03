from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import websockets


@dataclass
class CreatedUser:
    id: str
    username: str
    email: str
    phone_number: str
    role: str
    temp_password: str
    final_password: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a live QR attendance demo via HTTP API and persist a stats summary.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="API base URL.")
    parser.add_argument("--admin-username", default="admin", help="Admin username.")
    parser.add_argument("--admin-password", default="Admin123!", help="Admin password.")
    parser.add_argument(
        "--output",
        default="/tmp/universe_qr_attendance_stats_summary.json",
        help="Where to save the created demo data and API verification results.",
    )
    return parser


async def request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    token: str | None = None,
    expected_status: int = 200,
    **kwargs: Any,
) -> Any:
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = await client.request(method, path, headers=headers, **kwargs)
    if response.status_code != expected_status:
        raise RuntimeError(f"{method} {path} failed with {response.status_code}: {response.text}")
    if not response.content:
        return None
    return response.json()


async def login(client: httpx.AsyncClient, username: str, password: str) -> dict[str, Any]:
    return await request(
        client,
        "POST",
        "/auth/login",
        json={"username": username, "password": password},
    )


async def change_password(
    client: httpx.AsyncClient,
    token: str,
    *,
    current_password: str,
    new_password: str,
) -> None:
    await request(
        client,
        "POST",
        "/auth/password/change",
        token=token,
        json={"current_password": current_password, "new_password": new_password},
    )


async def create_user(
    client: httpx.AsyncClient,
    admin_token: str,
    *,
    username: str,
    full_name: str,
    email: str,
    phone_number: str,
    role: str,
    final_password: str,
) -> CreatedUser:
    payload = await request(
        client,
        "POST",
        "/admin/users",
        token=admin_token,
        json={
            "username": username,
            "full_name": full_name,
            "email": email,
            "phone_number": phone_number,
            "roles": [role],
        },
    )
    temp_password = str(payload["temp_password"])
    session = await login(client, username, temp_password)
    await change_password(
        client,
        session["access_token"],
        current_password=temp_password,
        new_password=final_password,
    )
    return CreatedUser(
        id=str(payload["id"]),
        username=username,
        email=email,
        phone_number=phone_number,
        role=role,
        temp_password=temp_password,
        final_password=final_password,
    )


def build_ws_url(base_url: str, ws_path: str, token: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    host = parsed.netloc
    return f"{scheme}://{host}{ws_path}?token={token}"


async def first_dynamic_qr_deeplink(base_url: str, ws_path: str, token: str) -> dict[str, Any]:
    ws_url = build_ws_url(base_url, ws_path, token)
    async with websockets.connect(ws_url) as websocket:
        raw_message = await asyncio.wait_for(websocket.recv(), timeout=10)
        payload = json.loads(raw_message)
        if payload.get("event") != "qr_slot":
            raise RuntimeError(f"Unexpected WebSocket payload: {payload}")
        return payload


async def main() -> None:
    args = build_parser().parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        await request(client, "GET", "/internal/ready")
        admin_tokens = await login(client, args.admin_username, args.admin_password)
        admin_token = str(admin_tokens["access_token"])

        faculty = await request(
            client,
            "POST",
            "/admin/faculties",
            token=admin_token,
            json={"code": f"QRF-{timestamp[-6:]}", "name": f"QR Faculty {timestamp[-6:]}"},
        )
        stream = await request(
            client,
            "POST",
            "/admin/streams",
            token=admin_token,
            json={"faculty_id": faculty["id"], "name": f"QR Stream {timestamp[-6:]}"},
        )
        group = await request(
            client,
            "POST",
            "/admin/groups",
            token=admin_token,
            json={
                "code": f"QR-DEMO-{timestamp[-6:]}",
                "name": f"QR Demo {timestamp[-6:]}",
                "faculty_id": faculty["id"],
                "stream_id": stream["id"],
            },
        )
        discipline = await request(
            client,
            "POST",
            "/admin/disciplines",
            token=admin_token,
            json={"code": f"QR-{timestamp[-4:]}", "name": f"QR Attendance Demo {timestamp[-4:]}"},
        )

        teacher = await create_user(
            client,
            admin_token,
            username=f"teacher_qr_{timestamp}",
            full_name=f"QR Teacher {timestamp[-4:]}",
            email=f"teacher.qr.{timestamp}@example.local",
            phone_number=f"+7701{timestamp[-7:]}1",
            role="teacher",
            final_password=f"TeacherQr{timestamp[-6:]}!",
        )
        students = [
            await create_user(
                client,
                admin_token,
                username=f"student_qr_{index}_{timestamp}",
                full_name=f"QR Student {index} {timestamp[-4:]}",
                email=f"student.qr.{index}.{timestamp}@example.local",
                phone_number=f"+7701{timestamp[-7:]}{index + 1}",
                role="student",
                final_password=f"StudentQr{index}{timestamp[-5:]}!",
            )
            for index in range(1, 4)
        ]

        teacher_assignment = await request(
            client,
            "POST",
            "/admin/assignments",
            token=admin_token,
            json={"teacher_id": teacher.id, "discipline_id": discipline["id"], "group_id": group["id"]},
        )

        transfer_date = datetime.now(UTC).date().isoformat()
        for student in students:
            await request(
                client,
                "POST",
                "/admin/student-transfer",
                token=admin_token,
                json={
                    "student_id": student.id,
                    "target_group_id": group["id"],
                    "transfer_date": transfer_date,
                },
            )

        now = datetime.now(UTC).replace(second=0, microsecond=0)
        lesson_specs = [
            {
                "label": "static_present",
                "starts_at": now - timedelta(minutes=2),
                "room": "A-201",
            },
            {
                "label": "static_late",
                "starts_at": now - timedelta(minutes=12),
                "room": "A-202",
                "late_threshold_minutes": 5,
            },
            {
                "label": "dynamic_present",
                "starts_at": now - timedelta(minutes=1),
                "room": "A-203",
            },
            {
                "label": "manual_absent",
                "starts_at": now - timedelta(minutes=3),
                "room": "A-204",
            },
        ]
        lessons: dict[str, dict[str, Any]] = {}
        for spec in lesson_specs:
            label = str(spec["label"])
            starts_at = spec["starts_at"]
            lesson = await request(
                client,
                "POST",
                "/admin/lessons",
                token=admin_token,
                json={
                    "group_id": group["id"],
                    "discipline_id": discipline["id"],
                    "teacher_id": teacher.id,
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1, minutes=20)).isoformat(),
                    "room": spec["room"],
                    "late_threshold_minutes": spec.get("late_threshold_minutes"),
                },
            )
            lessons[label] = lesson

        teacher_tokens = await login(client, teacher.username, teacher.final_password)
        teacher_token = str(teacher_tokens["access_token"])
        student_a = students[0]
        student_b = students[1]
        student_a_tokens = await login(client, student_a.username, student_a.final_password)
        student_b_tokens = await login(client, student_b.username, student_b.final_password)

        teacher_lessons = await request(client, "GET", "/teacher/lessons", token=teacher_token)
        student_a_schedule = await request(client, "GET", "/student/schedule", token=student_a_tokens["access_token"])

        static_present_qr = await request(
            client,
            "POST",
            "/teacher/qr/generate",
            token=teacher_token,
            json={"lesson_id": lessons["static_present"]["id"]},
        )
        static_present_mark = await request(
            client,
            "POST",
            "/student/attendance/mark-qr",
            token=student_a_tokens["access_token"],
            json={"qr_token": static_present_qr["deeplink"]},
        )

        static_late_qr = await request(
            client,
            "POST",
            "/teacher/qr/generate",
            token=teacher_token,
            json={"lesson_id": lessons["static_late"]["id"]},
        )
        static_late_mark = await request(
            client,
            "POST",
            "/student/attendance/mark-qr",
            token=student_a_tokens["access_token"],
            json={"qr_token": static_late_qr["deeplink"]},
        )

        dynamic_session = await request(
            client,
            "POST",
            "/teacher/qr/sessions/start",
            token=teacher_token,
            json={"lesson_id": lessons["dynamic_present"]["id"]},
        )
        dynamic_slot = await first_dynamic_qr_deeplink(
            args.base_url.rstrip("/"),
            dynamic_session["ws_url"],
            teacher_token,
        )
        dynamic_mark = await request(
            client,
            "POST",
            "/student/attendance/mark-qr",
            token=student_b_tokens["access_token"],
            json={"qr_token": dynamic_slot["deeplink"]},
        )
        dynamic_stop = await request(
            client,
            "POST",
            f"/teacher/qr/sessions/{dynamic_session['session_id']}/stop",
            token=teacher_token,
        )

        manual_absent = await request(
            client,
            "POST",
            "/teacher/attendance/correct",
            token=teacher_token,
            json={
                "lesson_id": lessons["manual_absent"]["id"],
                "student_id": student_a.id,
                "status": "absent",
                "reason": "Manual absent seed for statistics demo",
            },
        )

        date_from = (now.date() - timedelta(days=1)).isoformat()
        date_to = (now.date() + timedelta(days=1)).isoformat()

        student_a_summary = await request(
            client,
            "GET",
            "/student/attendance/summary",
            token=student_a_tokens["access_token"],
            params={"date_from": date_from, "date_to": date_to},
        )
        student_a_history = await request(
            client,
            "GET",
            "/student/attendance/history",
            token=student_a_tokens["access_token"],
            params={"date_from": date_from, "date_to": date_to},
        )
        student_b_summary = await request(
            client,
            "GET",
            "/student/attendance/summary",
            token=student_b_tokens["access_token"],
            params={"date_from": date_from, "date_to": date_to},
        )
        teacher_report = await request(
            client,
            "GET",
            "/teacher/reports/attendance",
            token=teacher_token,
            params={"date_from": date_from, "date_to": date_to, "group_id": group["id"]},
        )
        admin_report = await request(
            client,
            "GET",
            "/admin/reports/attendance",
            token=admin_token,
            params={
                "date_from": date_from,
                "date_to": date_to,
                "group_id": group["id"],
                "teacher_id": teacher.id,
            },
        )
        admin_lates = await request(
            client,
            "GET",
            "/admin/reports/lates",
            token=admin_token,
            params={"date_from": date_from, "date_to": date_to, "group_id": group["id"], "page_size": 50},
        )
        roster_snapshots = {
            label: await request(
                client,
                "GET",
                f"/teacher/lessons/{lesson['id']}/attendance",
                token=teacher_token,
            )
            for label, lesson in lessons.items()
        }

    summary = {
        "base_url": args.base_url.rstrip("/"),
        "created_at": datetime.now(UTC).isoformat(),
        "faculty": faculty,
        "stream": stream,
        "group": group,
        "discipline": discipline,
        "teacher_assignment": teacher_assignment,
        "users": {
            "teacher": asdict(teacher),
            "students": [asdict(student) for student in students],
        },
        "lessons": lessons,
        "api_verification": {
            "teacher_lessons_count": len(teacher_lessons),
            "student_a_schedule_count": len(student_a_schedule),
            "static_present_mark": static_present_mark,
            "static_late_mark": static_late_mark,
            "dynamic_session": dynamic_session,
            "dynamic_slot": dynamic_slot,
            "dynamic_mark": dynamic_mark,
            "dynamic_stop": dynamic_stop,
            "manual_absent": manual_absent,
        },
        "reports": {
            "student_a_summary": student_a_summary,
            "student_a_history": student_a_history,
            "student_b_summary": student_b_summary,
            "teacher_group_report": teacher_report,
            "admin_group_report": admin_report,
            "admin_lates": admin_lates,
            "roster_snapshots": roster_snapshots,
        },
        "expected_demo_shape": {
            "student_a": {"present": 1, "late": 1, "absent": 1},
            "student_b": {"present": 1, "late": 0, "absent": 0},
            "group_totals": {"present": 2, "late": 1, "absent": 1},
        },
    }

    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "group_code": group["code"], "teacher": teacher.username}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
