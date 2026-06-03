import logging
import sys
from collections.abc import Mapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars

_DEF_LEVEL = logging.INFO
_SENSITIVE_KEYS = (
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "init_data",
    "hash",
    "signature",
)


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=_DEF_LEVEL)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_DEF_LEVEL),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)


def bind_log_context(**values: Any) -> None:
    payload = {key: value for key, value in values.items() if value is not None}
    if payload:
        bind_contextvars(**payload)


def clear_log_context() -> None:
    clear_contextvars()


def current_log_context() -> dict[str, Any]:
    return dict(get_contextvars())


def sanitize_log_data(value: Any, *, max_depth: int = 4) -> Any:
    if max_depth <= 0:
        return "[truncated]"
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, entry in value.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in _SENSITIVE_KEYS):
                sanitized[str(key)] = "[redacted]"
            else:
                sanitized[str(key)] = sanitize_log_data(entry, max_depth=max_depth - 1)
        return sanitized
    if isinstance(value, list):
        return [sanitize_log_data(item, max_depth=max_depth - 1) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_log_data(item, max_depth=max_depth - 1) for item in value)
    if isinstance(value, str):
        if len(value) > 4_000:
            return f"{value[:4_000]}...[truncated]"
        return value
    return value
