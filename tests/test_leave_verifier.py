"""Leave verifier: task-derived expectations, uniqueness, reject wrong writes."""

from __future__ import annotations

import httpx
import pytest

from agent.config import Settings
from agent.memory import Memory
from agent.models import Observation, ToolCall
from agent.verifier import Verifier

LEAVE_TASK = (
    "File a leave request for employee 42 from 2025-04-01 to 2025-04-05 "
    "with reason family."
)


async def _post_leave(
    base: str,
    *,
    start: str = "2025-04-01",
    end: str = "2025-04-05",
    reason: str = "family",
    n: int = 1,
) -> None:
    async with httpx.AsyncClient(base_url=base) as client:
        for _ in range(n):
            r = await client.post(
                "/api/leave",
                json={
                    "employee_id": 42,
                    "start_date": start,
                    "end_date": end,
                    "reason": reason,
                },
            )
            assert r.status_code in {200, 201}


@pytest.mark.asyncio
async def test_leave_verifier_passes_on_exactly_one(mock_app: str) -> None:
    await _post_leave(mock_app, n=1)
    mem = Memory(task=LEAVE_TASK)
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is True
    assert any("Exactly one leave record" in c for c in result.checks)
    assert result.details["leave_expected"]["source"] == "task_text"


@pytest.mark.asyncio
async def test_leave_verifier_fails_on_duplicates(mock_app: str) -> None:
    await _post_leave(mock_app, n=2)
    mem = Memory(task=LEAVE_TASK)
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is False
    assert any("duplicate" in c.lower() for c in result.checks)
    assert result.details.get("leave_match_count") == 2


@pytest.mark.asyncio
async def test_leave_verifier_uses_task_text_not_agent_memory(mock_app: str) -> None:
    """Missing remember is fine; expectations still come from the task."""
    await _post_leave(mock_app, n=1)
    mem = Memory(task=LEAVE_TASK)
    # Poison scratchpad with the wrong start date — must not become expected.
    mem.remember("leave_start", "2025-04-02", 0)
    mem.remember("leave_end", "2025-04-05", 0)
    mem.remember("leave_reason", "family", 0)
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is True
    assert result.details["leave_expected"]["start_date"] == "2025-04-01"


@pytest.mark.asyncio
async def test_leave_verifier_rejects_wrong_posted_date(mock_app: str) -> None:
    """Negative test: agent POSTs 2025-04-02 when the task asks for 2025-04-01."""
    await _post_leave(mock_app, start="2025-04-02", end="2025-04-05", reason="family")
    mem = Memory(task=LEAVE_TASK)
    mem.add_step(
        0,
        "file leave with wrong start",
        ToolCall(
            tool="api",
            args={
                "method": "POST",
                "path": "/api/leave",
                "json": {
                    "employee_id": 42,
                    "start_date": "2025-04-02",
                    "end_date": "2025-04-05",
                    "reason": "family",
                },
            },
        ),
        Observation(ok=True, data={"status_code": 200}),
    )
    # Even if the agent "remembers" the wrong date it posted, expected is task text.
    mem.remember("leave_start", "2025-04-02", 1)
    mem.remember("leave_end", "2025-04-05", 1)
    mem.remember("leave_reason", "family", 1)

    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is False
    assert result.details["leave_expected"]["start_date"] == "2025-04-01"
    assert any("No leave record matching" in c for c in result.checks)
