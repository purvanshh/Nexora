"""E2E: permanent 500 → retries exhausted → ask_user abort → failed."""

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


def _script() -> list[LLMResponse]:
    return [
        LLMResponse(
            thought="List mail",
            tool_call=ToolCall(tool="api", args={"method": "GET", "path": "/api/mail"}),
        ),
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
            thought="Remember due date",
            tool_call=ToolCall(
                tool="remember",
                args={"key": "invoice_due_date", "value": "2025-03-15"},
            ),
        ),
        LLMResponse(
            thought="Remember invoice id",
            tool_call=ToolCall(
                tool="remember", args={"key": "invoice_id", "value": "INV-4471"}
            ),
        ),
        LLMResponse(
            thought="Submit invoice — will permanently 500",
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
        # Should not be reached if escalation aborts after exhausted retries.
        LLMResponse(
            thought="should not run",
            is_finish=True,
            summary="unexpected finish",
        ),
    ]


@pytest.mark.asyncio
async def test_e2e_escalation_abort_on_permanent_fail(
    mock_app_permanent_fail: str, workspace: Path, tmp_path: Path
) -> None:
    settings = Settings(
        openai_api_key="unused",
        mock_app_url=mock_app_permanent_fail,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
        headless=True,
        agent_retries=2,
    )
    answers: list[str] = []

    def ask_cb(question: str, options: list[str] | None) -> str:
        answers.append(question)
        return "a"  # abort

    registry = get_default_registry(
        settings,
        ask_callback=ask_cb,
        evidence_dir=tmp_path / "shots",
    )
    result = await run(
        PRIMARY,
        llm=StubLLMClient(_script()),
        registry=registry,
        settings=settings,
    )

    assert result.status == "failed"
    assert result.user_aborted is True
    assert "could not complete" in result.summary.lower()
    assert "abort" in result.summary.lower()
    assert result.verification is not None
    assert result.verification.method == "skipped_abort"
    assert answers, "expected an escalation prompt"
    assert any("retry" in a.lower() or "exhaust" in a.lower() for a in answers)

    # Retries exhausted should be visible on the failed POST observation.
    post_steps = [
        s
        for s in result.steps
        if s.tool_call
        and s.tool_call.tool == "api"
        and str(s.tool_call.args.get("method", "")).upper() == "POST"
    ]
    assert post_steps
    obs = post_steps[0].observation
    assert obs is not None
    assert obs.ok is False
    assert obs.data is not None
    assert obs.data.get("retries_exhausted") is True
    assert obs.data.get("attempts") == 3  # 1 try + 2 retries

    # Finance DB must remain empty — permanent fail never wrote.
    async with httpx.AsyncClient(base_url=mock_app_permanent_fail) as client:
        listed = (await client.get("/api/invoices")).json()
    assert listed == []
