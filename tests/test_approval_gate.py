"""Pre-write approval gate: POST pauses for approve/reject."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent.config import Settings
from agent.loop import run
from agent.models import LLMResponse, ToolCall
from agent.planner import StubLLMClient
from agent.tools.registry import get_default_registry

PRIMARY = (
    "Find the latest invoice from Acme Corp in the mail app, extract amount and "
    "due date, enter it into the finance system, and confirm it's saved."
)


def _script_through_post() -> list[LLMResponse]:
    return [
        LLMResponse(
            thought="Remember sender",
            tool_call=ToolCall(
                tool="remember", args={"key": "sender", "value": "Acme Corp"}
            ),
        ),
        LLMResponse(
            thought="Remember amount",
            tool_call=ToolCall(
                tool="remember", args={"key": "invoice_amount", "value": 1250.0}
            ),
        ),
        LLMResponse(
            thought="Remember due",
            tool_call=ToolCall(
                tool="remember",
                args={"key": "invoice_due_date", "value": "2025-03-15"},
            ),
        ),
        LLMResponse(
            thought="Remember id",
            tool_call=ToolCall(
                tool="remember", args={"key": "invoice_id", "value": "INV-4471"}
            ),
        ),
        LLMResponse(
            thought="Submit invoice",
            tool_call=ToolCall(
                tool="api",
                args={
                    "method": "POST",
                    "path": "/api/invoices",
                    "json": {
                        "sender": "Acme Corp",
                        "amount": 1250.0,
                        "due_date": "2025-03-15",
                        "invoice_id": "INV-4471",
                    },
                },
            ),
        ),
        LLMResponse(thought="done", is_finish=True, summary="should not finish if rejected"),
    ]


@pytest.mark.asyncio
async def test_write_approval_reject_blocks_post(
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
    prompts: list[str] = []

    def ask_cb(question: str, options: list[str] | None) -> str:
        prompts.append(question)
        return "reject"

    registry = get_default_registry(
        settings, ask_callback=ask_cb, evidence_dir=tmp_path / "shots"
    )
    result = await run(
        PRIMARY,
        llm=StubLLMClient(_script_through_post()),
        registry=registry,
        settings=settings,
    )

    assert result.status == "failed"
    assert result.user_aborted is True
    assert "rejected write approval" in result.summary.lower()
    assert prompts and any("approve" in p.lower() or "payload" in p.lower() for p in prompts)
    assert result.verification is not None
    assert result.verification.details.get("reason") == "write_rejected"

    async with httpx.AsyncClient(base_url=mock_app) as client:
        listed = (await client.get("/api/invoices")).json()
    assert listed == []


@pytest.mark.asyncio
async def test_write_approval_approve_allows_post(
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

    script = _script_through_post()[:-1] + [
        LLMResponse(
            thought="Confirm UI",
            tool_call=ToolCall(
                tool="browser",
                args={"action": "goto", "url": "/finance/invoices"},
            ),
        ),
        LLMResponse(
            thought="done",
            is_finish=True,
            summary="Submitted INV-4471",
        ),
    ]
    registry = get_default_registry(
        settings, ask_callback=ask_cb, evidence_dir=tmp_path / "shots"
    )
    result = await run(
        PRIMARY,
        llm=StubLLMClient(script),
        registry=registry,
        settings=settings,
    )
    assert result.status == "success"
    async with httpx.AsyncClient(base_url=mock_app) as client:
        record = (await client.get("/api/invoices/INV-4471")).json()
    assert record["invoice_id"] == "INV-4471"
