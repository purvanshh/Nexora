"""Leave verifier requires exactly one matching record."""

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


async def _seed_leave(base: str, *, n: int = 1) -> None:
    async with httpx.AsyncClient(base_url=base) as client:
        for _ in range(n):
            r = await client.post(
                "/api/leave",
                json={
                    "employee_id": 42,
                    "start_date": "2025-04-01",
                    "end_date": "2025-04-05",
                    "reason": "family",
                },
            )
            assert r.status_code in {200, 201}


@pytest.mark.asyncio
async def test_leave_verifier_passes_on_exactly_one(mock_app: str) -> None:
    await _seed_leave(mock_app, n=1)
    mem = Memory(task=LEAVE_TASK)
    mem.remember("employee_id", 42, 0)
    mem.remember("leave_start", "2025-04-01", 0)
    mem.remember("leave_end", "2025-04-05", 0)
    mem.remember("leave_reason", "family", 0)
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is True
    assert any("Exactly one leave record" in c for c in result.checks)


@pytest.mark.asyncio
async def test_leave_verifier_fails_on_duplicates(mock_app: str) -> None:
    await _seed_leave(mock_app, n=2)
    mem = Memory(task=LEAVE_TASK)
    mem.remember("employee_id", 42, 0)
    mem.remember("leave_start", "2025-04-01", 0)
    mem.remember("leave_end", "2025-04-05", 0)
    mem.remember("leave_reason", "family", 0)
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is False
    assert any("duplicate" in c.lower() for c in result.checks)
    assert result.details.get("leave_match_count") == 2


@pytest.mark.asyncio
async def test_leave_verifier_uses_post_body_when_facts_missing(mock_app: str) -> None:
    await _seed_leave(mock_app, n=1)
    mem = Memory(task=LEAVE_TASK)
    mem.add_step(
        0,
        "file leave",
        ToolCall(
            tool="api",
            args={
                "method": "POST",
                "path": "/api/leave",
                "json": {
                    "employee_id": 42,
                    "start_date": "2025-04-01",
                    "end_date": "2025-04-05",
                    "reason": "family",
                },
            },
        ),
        Observation(ok=True, data={"status_code": 200}),
    )
    result = await Verifier(Settings(mock_app_url=mock_app)).verify(LEAVE_TASK, mem)
    assert result.passed is True
    assert result.details["leave_expected"]["start_date"] == "2025-04-01"
