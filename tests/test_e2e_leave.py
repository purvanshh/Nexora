"""E2E: second write-type task (HR leave) with approval + scope check."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent.config import Settings
from agent.loop import run
from agent.models import LLMResponse, ToolCall
from agent.planner import StubLLMClient
from agent.tools.registry import get_default_registry

LEAVE = (
    "File a leave request for employee 42 from 2025-04-01 to 2025-04-05 "
    "with reason family."
)


def _script() -> list[LLMResponse]:
    return [
        LLMResponse(
            thought="Confirm employee",
            tool_call=ToolCall(
                tool="api", args={"method": "GET", "path": "/api/employees/42"}
            ),
        ),
        LLMResponse(
            thought="Remember employee",
            tool_call=ToolCall(
                tool="remember", args={"key": "employee_id", "value": 42}
            ),
        ),
        LLMResponse(
            thought="Remember start",
            tool_call=ToolCall(
                tool="remember", args={"key": "leave_start", "value": "2025-04-01"}
            ),
        ),
        LLMResponse(
            thought="Remember end",
            tool_call=ToolCall(
                tool="remember", args={"key": "leave_end", "value": "2025-04-05"}
            ),
        ),
        LLMResponse(
            thought="Remember reason",
            tool_call=ToolCall(
                tool="remember", args={"key": "leave_reason", "value": "family"}
            ),
        ),
        LLMResponse(
            thought="File leave",
            tool_call=ToolCall(
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
        ),
        LLMResponse(
            thought="done",
            is_finish=True,
            summary="Filed leave for employee 42",
        ),
    ]


@pytest.mark.asyncio
async def test_e2e_leave_write(
    mock_app: str, workspace: Path, tmp_path: Path
) -> None:
    settings = Settings(
        openai_api_key="unused",
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
        headless=True,
        require_write_approval=True,
    )

    def ask_cb(question: str, options: list[str] | None) -> str:
        opts = [o.lower() for o in (options or [])]
        if "approve" in opts:
            return "approve"
        return "abort"

    registry = get_default_registry(
        settings, ask_callback=ask_cb, evidence_dir=tmp_path / "shots"
    )
    result = await run(
        LEAVE,
        llm=StubLLMClient(_script()),
        registry=registry,
        settings=settings,
    )
    assert result.status == "success"
    assert result.verification is not None
    assert result.verification.passed is True
    assert "leave" in result.summary.lower()

    async with httpx.AsyncClient(base_url=mock_app) as client:
        leaves = (await client.get("/api/leave", params={"employee_id": 42})).json()
        invoices = (await client.get("/api/invoices")).json()
    assert len(leaves) == 1
    assert leaves[0]["reason"] == "family"
    assert invoices == []
