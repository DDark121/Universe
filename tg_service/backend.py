from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from tg_service.config import TGServiceSettings
from tg_service.logging import get_logger, sanitize_log_data
from tg_service.security import build_backend_token

logger = get_logger(__name__)


class BackendClientError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class BackendClient:
    def __init__(self, settings: TGServiceSettings):
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.backend_api_base_url,
            timeout=settings.backend_timeout_seconds,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self, telegram_id: int | None = None, *, correlation_id: str | None = None) -> dict[str, str]:
        headers = {
            "X-Service-Token": build_backend_token(self.settings),
            "Content-Type": "application/json",
        }
        if telegram_id is not None:
            headers["X-Telegram-Id"] = str(telegram_id)
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        telegram_id: int | None = None,
        json: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        correlation_id = str(uuid4())
        logger.info(
            "tg_backend_request",
            correlation_id=correlation_id,
            method=method,
            path=path,
            telegram_id=telegram_id,
            has_json=bool(json),
            params=sanitize_log_data(params) if params else None,
        )
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
                headers=self._headers(telegram_id, correlation_id=correlation_id),
            )
        except httpx.HTTPError as exc:
            logger.exception(
                "tg_backend_transport_error",
                correlation_id=correlation_id,
                method=method,
                path=path,
                telegram_id=telegram_id,
            )
            raise BackendClientError(502, "Backend request failed") from exc

        backend_correlation_id = response.headers.get("X-Correlation-ID")
        if response.status_code >= 400:
            detail = response.text
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or payload.get("message") or detail)
            log_method = logger.error if response.status_code >= 500 else logger.warning
            log_method(
                "tg_backend_response_error",
                correlation_id=correlation_id,
                backend_correlation_id=backend_correlation_id,
                method=method,
                path=path,
                telegram_id=telegram_id,
                status_code=response.status_code,
                detail=detail,
            )
            raise BackendClientError(response.status_code, detail)

        logger.info(
            "tg_backend_response",
            correlation_id=correlation_id,
            backend_correlation_id=backend_correlation_id,
            method=method,
            path=path,
            telegram_id=telegram_id,
            status_code=response.status_code,
        )
        if not response.content:
            return {}
        return response.json()

    async def get_bootstrap(self, telegram_id: int) -> dict:
        return await self._request("GET", f"/tg/bootstrap/{telegram_id}", telegram_id=telegram_id)

    async def exchange_auth(self, telegram_id: int) -> dict:
        return await self._request(
            "POST",
            "/tg/auth/exchange",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id},
        )

    async def create_binding_request(
        self,
        *,
        telegram_id: int,
        telegram_username: str | None,
        full_name: str | None,
        group_code: str | None,
        note: str | None,
    ) -> dict:
        return await self._request(
            "POST",
            "/tg/binding-requests",
            telegram_id=telegram_id,
            json={
                "telegram_id": telegram_id,
                "telegram_username": telegram_username,
                "full_name": full_name,
                "group_code": group_code,
                "note": note,
            },
        )

    async def mark_attendance(self, *, telegram_id: int, qr_token: str) -> dict:
        return await self._request(
            "POST",
            "/tg/attendance/mark",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id, "qr_token": qr_token},
        )

    async def mark_button_attendance(self, *, telegram_id: int, lesson_id: str) -> dict:
        return await self._request(
            "POST",
            "/tg/student/attendance/button",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id, "lesson_id": lesson_id},
        )

    async def get_context(self, telegram_id: int) -> dict:
        return await self._request("GET", f"/tg/context/{telegram_id}", telegram_id=telegram_id)

    async def get_student_schedule(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/tg/student/schedule/{telegram_id}", telegram_id=telegram_id)

    async def get_student_summary(self, telegram_id: int) -> dict:
        return await self._request("GET", f"/tg/student/attendance-summary/{telegram_id}", telegram_id=telegram_id)

    async def get_student_rating(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/tg/student/rating/{telegram_id}", telegram_id=telegram_id)

    async def get_student_warnings(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/tg/student/warnings/{telegram_id}", telegram_id=telegram_id)

    async def get_student_faq(
        self,
        telegram_id: int,
        *,
        query: str | None = None,
        category_id: str | None = None,
    ) -> list[dict]:
        params: dict[str, Any] = {}
        if query:
            params["query"] = query
        if category_id:
            params["category_id"] = category_id
        return await self._request(
            "GET",
            f"/tg/student/faq/{telegram_id}",
            telegram_id=telegram_id,
            params=params or None,
        )

    async def submit_student_absence_reason(
        self,
        *,
        telegram_id: int,
        lesson_id: str,
        reason_type: str,
        comment: str | None = None,
        is_predeclared: bool = False,
    ) -> dict:
        return await self._request(
            "POST",
            f"/tg/student/absence-reasons/{telegram_id}",
            telegram_id=telegram_id,
            json={
                "lesson_id": lesson_id,
                "reason_type": reason_type,
                "comment": comment,
                "is_predeclared": is_predeclared,
            },
        )

    async def get_teacher_lessons(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/tg/teacher/lessons/{telegram_id}", telegram_id=telegram_id)

    async def get_teacher_lesson_attendance(self, *, telegram_id: int, lesson_id: str) -> dict:
        return await self._request(
            "GET",
            f"/tg/teacher/lessons/{telegram_id}/{lesson_id}/attendance",
            telegram_id=telegram_id,
        )

    async def generate_teacher_qr(self, *, telegram_id: int, lesson_id: str) -> dict:
        return await self._request(
            "POST",
            "/tg/teacher/qr/generate",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id, "lesson_id": lesson_id},
        )

    async def get_teacher_absence_reasons(self, telegram_id: int) -> list[dict]:
        return await self._request("GET", f"/tg/teacher/absence-reasons/{telegram_id}", telegram_id=telegram_id)

    async def moderate_teacher_reason(
        self,
        *,
        telegram_id: int,
        reason_id: str,
        status: str,
        comment: str | None = None,
    ) -> dict:
        return await self._request(
            "POST",
            "/tg/teacher/absence-reasons/moderate",
            telegram_id=telegram_id,
            json={
                "telegram_id": telegram_id,
                "reason_id": reason_id,
                "status": status,
                "comment": comment,
            },
        )

    async def teacher_broadcast(self, *, telegram_id: int, group_id: str, message: str) -> dict:
        return await self._request(
            "POST",
            "/tg/teacher/broadcasts",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id, "group_id": group_id, "message": message},
        )

    async def upsert_activity_score(
        self,
        *,
        telegram_id: int,
        lesson_id: str,
        student_id: str,
        score: float,
        comment: str | None = None,
    ) -> dict:
        return await self._request(
            "POST",
            "/tg/teacher/activity",
            telegram_id=telegram_id,
            json={
                "telegram_id": telegram_id,
                "lesson_id": lesson_id,
                "student_id": student_id,
                "score": score,
                "comment": comment,
            },
        )

    async def assistant_reply(self, *, telegram_id: int, message: str) -> dict:
        return await self._request(
            "POST",
            "/tg/assistant/reply",
            telegram_id=telegram_id,
            json={"telegram_id": telegram_id, "message": message},
        )
