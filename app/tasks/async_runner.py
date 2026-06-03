from __future__ import annotations

import asyncio
import atexit
from collections.abc import Awaitable

_loop: asyncio.AbstractEventLoop | None = None


def _close_loop() -> None:
    global _loop
    if _loop is None or _loop.is_closed():
        return
    _loop.close()
    _loop = None


atexit.register(_close_loop)


def run_async[T](coro: Awaitable[T]) -> T:
    """Run Celery coroutines on a stable per-process loop.

    Celery tasks are synchronous, but our DB/Redis integrations are async. Reusing
    a single loop avoids binding pooled asyncpg connections to a fresh loop on
    every task invocation.
    """

    global _loop

    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

    return _loop.run_until_complete(coro)
