from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx


@dataclass
class CreatedUser:
    id: str
    username: str
    email: str
    phone_number: str
    role: str
    temp_password: str
    final_password: str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap a full demo study group via live HTTP API calls.")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1", help="API base URL.")
    parser.add_argument("--admin-username", default="admin", help="Admin username.")
    parser.add_argument("--admin-password", default="Admin123!", help="Admin password.")
    parser.add_argument(
        "--output",
        default="/tmp/universe_demo_bootstrap_summary.json",
        help="Where to store the created credentials and IDs.",
    )
    return parser


def _request(
    client: httpx.Client,
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
    response = client.request(method, path, headers=headers, **kwargs)
    if response.status_code != expected_status:
        raise RuntimeError(f"{method} {path} failed with {response.status_code}: {response.text}")
    if not response.content:
        return None
    return response.json()


def _login(client: httpx.Client, username: str, password: str) -> dict[str, Any]:
    return _request(
        client,
        "POST",
        "/auth/login",
        json={"username": username, "password": password},
    )


def _change_password(client: httpx.Client, token: str, current_password: str, new_password: str) -> None:
    _request(
        client,
        "POST",
        "/auth/password/change",
        token=token,
        json={"current_password": current_password, "new_password": new_password},
    )


def _create_user(
    client: httpx.Client,
    token: str,
    *,
    username: str,
    full_name: str,
    email: str,
    phone_number: str,
    role: str,
    final_password: str,
) -> CreatedUser:
    payload = _request(
        client,
        "POST",
        "/admin/users",
        token=token,
        json={
            "username": username,
            "full_name": full_name,
            "email": email,
            "phone_number": phone_number,
            "roles": [role],
        },
    )
    temp_password = str(payload["temp_password"])
    login_payload = _login(client, username, temp_password)
    _change_password(client, login_payload["access_token"], temp_password, final_password)
    return CreatedUser(
        id=str(payload["id"]),
        username=username,
        email=email,
        phone_number=phone_number,
        role=role,
        temp_password=temp_password,
        final_password=final_password,
    )


def main() -> None:
    args = _build_parser().parse_args()
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        ready = client.get("/internal/ready")
        if ready.status_code != 200:
            raise RuntimeError(f"API is not ready: {ready.status_code} {ready.text}")

        admin_tokens = _login(client, args.admin_username, args.admin_password)
        admin_access = str(admin_tokens["access_token"])

        faculty = _request(
            client,
            "POST",
            "/admin/faculties",
            token=admin_access,
            json={"code": f"FIT-{timestamp}", "name": f"Faculty Demo {timestamp}"},
        )
        stream = _request(
            client,
            "POST",
            "/admin/streams",
            token=admin_access,
            json={"faculty_id": faculty["id"], "name": f"SE Demo Stream {timestamp}"},
        )
        group = _request(
            client,
            "POST",
            "/admin/groups",
            token=admin_access,
            json={
                "code": f"SE-DEMO-{timestamp[-6:]}",
                "name": f"SE Demo {timestamp[-6:]}",
                "faculty_id": faculty["id"],
                "stream_id": stream["id"],
            },
        )
        discipline = _request(
            client,
            "POST",
            "/admin/disciplines",
            token=admin_access,
            json={"code": f"DB-{timestamp[-4:]}", "name": f"Databases Demo {timestamp[-4:]}"},
        )

        tutor = _create_user(
            client,
            admin_access,
            username=f"tutor_{timestamp}",
            full_name=f"Demo Tutor {timestamp[-4:]}",
            email=f"tutor.{timestamp}@example.local",
            phone_number=f"+7701{timestamp[-7:]}1",
            role="curator",
            final_password=f"Tutor{timestamp[-6:]}!",
        )
        teacher = _create_user(
            client,
            admin_access,
            username=f"teacher_{timestamp}",
            full_name=f"Demo Teacher {timestamp[-4:]}",
            email=f"teacher.{timestamp}@example.local",
            phone_number=f"+7701{timestamp[-7:]}2",
            role="teacher",
            final_password=f"Teacher{timestamp[-6:]}!",
        )
        students = [
            _create_user(
                client,
                admin_access,
                username=f"student_{index}_{timestamp}",
                full_name=f"Demo Student {index} {timestamp[-4:]}",
                email=f"student.{index}.{timestamp}@example.local",
                phone_number=f"+7701{timestamp[-7:]}{index + 2}",
                role="student",
                final_password=f"Student{index}{timestamp[-5:]}!",
            )
            for index in range(1, 4)
        ]

        tutor_assignment = _request(
            client,
            "POST",
            "/admin/tutor-assignments",
            token=admin_access,
            json={"tutor_user_id": tutor.id, "group_id": group["id"]},
        )
        teacher_assignment = _request(
            client,
            "POST",
            "/admin/assignments",
            token=admin_access,
            json={"teacher_id": teacher.id, "discipline_id": discipline["id"], "group_id": group["id"]},
        )

        today_iso = datetime.now(UTC).date().isoformat()
        for student in students:
            _request(
                client,
                "POST",
                "/admin/student-transfer",
                token=admin_access,
                json={
                    "student_id": student.id,
                    "target_group_id": group["id"],
                    "transfer_date": today_iso,
                },
            )

        lesson_starts = [
            datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=1, hours=9),
            datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=3, hours=11),
        ]
        lessons = []
        for starts_at, room in zip(lesson_starts, ("A-101", "A-103"), strict=True):
            lesson = _request(
                client,
                "POST",
                "/admin/lessons",
                token=admin_access,
                json={
                    "group_id": group["id"],
                    "discipline_id": discipline["id"],
                    "teacher_id": teacher.id,
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1, minutes=30)).isoformat(),
                    "room": room,
                },
            )
            lessons.append(lesson)

        admin_users = _request(
            client,
            "GET",
            "/admin/users",
            token=admin_access,
            params={"group_id": group["id"], "search": students[0].phone_number, "page_size": 500},
        )
        admin_assignments = _request(client, "GET", "/admin/assignments", token=admin_access, params={"page_size": 500})
        admin_tutor_assignments = _request(
            client,
            "GET",
            "/admin/tutor-assignments",
            token=admin_access,
            params={"group_id": group["id"], "page_size": 500},
        )
        admin_lessons = _request(client, "GET", "/admin/lessons", token=admin_access, params={"page_size": 500})

        tutor_tokens = _login(client, tutor.username, tutor.final_password)
        tutor_groups = _request(client, "GET", "/admin/tutor/groups", token=tutor_tokens["access_token"])

        teacher_tokens = _login(client, teacher.username, teacher.final_password)
        teacher_groups = _request(client, "GET", "/teacher/groups", token=teacher_tokens["access_token"])
        teacher_lessons = _request(client, "GET", "/teacher/lessons", token=teacher_tokens["access_token"])

        student_tokens = _login(client, students[0].username, students[0].final_password)
        student_me = _request(client, "GET", "/auth/me", token=student_tokens["access_token"])
        student_profile = _request(client, "GET", "/student/profile", token=student_tokens["access_token"])
        student_schedule = _request(client, "GET", "/student/schedule", token=student_tokens["access_token"])

    summary = {
        "base_url": args.base_url,
        "generated_at": datetime.now(UTC).isoformat(),
        "faculty": faculty,
        "stream": stream,
        "group": group,
        "discipline": discipline,
        "users": {
            "tutor": tutor.__dict__,
            "teacher": teacher.__dict__,
            "students": [student.__dict__ for student in students],
        },
        "assignments": {
            "tutor": tutor_assignment,
            "teacher": teacher_assignment,
        },
        "lessons": lessons,
        "checks": {
            "admin_users_group_total": admin_users["meta"]["total"],
            "admin_assignment_total": admin_assignments["meta"]["total"],
            "admin_tutor_assignment_total": admin_tutor_assignments["meta"]["total"],
            "admin_lesson_total": admin_lessons["meta"]["total"],
            "tutor_groups": tutor_groups,
            "teacher_groups": teacher_groups,
            "teacher_lesson_count": len(teacher_lessons),
            "student_me": student_me,
            "student_profile": student_profile,
            "student_schedule_count": len(student_schedule),
        },
    }

    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Bootstrap completed. Summary written to {output_path}")


if __name__ == "__main__":
    main()
