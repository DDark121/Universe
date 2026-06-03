from __future__ import annotations

import asyncio

from app.tasks.async_runner import run_async


async def _loop_id() -> int:
    return id(asyncio.get_running_loop())


def test_run_async_reuses_single_event_loop():
    first = run_async(_loop_id())
    second = run_async(_loop_id())

    assert first == second
