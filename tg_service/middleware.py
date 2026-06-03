from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from tg_service.logging import bind_log_context, clear_log_context, current_log_context, get_logger

logger = get_logger(__name__)


def _should_warn(status_code: int) -> bool:
    return status_code in {401, 403, 429}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
        telegram_id = request.headers.get("X-Telegram-Id")
        client_ip = request.client.host if request.client else None
        clear_log_context()
        bind_log_context(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
            telegram_id=telegram_id,
            client_ip=client_ip,
        )
        request.state.correlation_id = correlation_id
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_unhandled_exception",
                correlation_id=correlation_id,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            clear_log_context()
            raise

        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        context = current_log_context()
        log_payload = {
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": context.get("user_id"),
            "telegram_id": context.get("telegram_id"),
            "service_name": context.get("service_name"),
        }
        if response.status_code >= 500:
            logger.error("request_completed", **log_payload)
        elif _should_warn(response.status_code):
            logger.warning("request_completed", **log_payload)
        else:
            logger.info("request_completed", **log_payload)
        clear_log_context()
        return response
