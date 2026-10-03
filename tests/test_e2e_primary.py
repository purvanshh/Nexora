"""E2E primary scenario with stubbed LLM and real tools + mock app."""

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
            thought="List mail via API",
            tool_call=ToolCall(tool="api", args={"method": "GET", "path": "/api/mail"}),
        ),
        LLMResponse(
            thought="Open latest Acme invoice email mail-003",
            tool_call=ToolCall(
                tool="api", args={"method": "GET", "path": "/api/mail/mail-003"}
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
            thought="Remember sender",
            tool_call=ToolCall(
                tool="remember", args={"key": "sender", "value": "Acme Corp"}
            ),
        ),
        LLMResponse(
            thought="Remember business invoice id",
            tool_call=ToolCall(
                tool="remember", args={"key": "invoice_id", "value": "INV-4471"}
            ),
        ),
        LLMResponse(
            thought="Submit to finance API",
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
                        "source_mail_id": "mail-003",
                    },
                },
            ),
        ),
        LLMResponse(
            thought="Task complete",
            is_finish=True,
            summary=(
                "Submitted invoice INV-4471 from Acme Corp for $1,250.00 "
                "due 2025-03-15 to the finance system."
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_e2e_primary_stubbed_llm(
    mock_app: str, workspace: Path, tmp_path: Path
) -> None:
    settings = Settings(
        openai_api_key="unused",
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
        headless=True,
        agent_retries=2,
    )
    registry = get_default_registry(
        settings,
        ask_callback=lambda q, o: "continue",
        evidence_dir=tmp_path / "shots",
    )
    llm = StubLLMClient(_script())
    try:
        result = await run(
            PRIMARY,
            llm=llm,
            registry=registry,
            settings=settings,
        )
    finally:
        await registry.aclose()

    assert result.status == "success"
    assert result.verification is not None
    assert result.verification.passed is True

    async with httpx.AsyncClient(base_url=mock_app) as client:
        listed = (await client.get("/api/invoices", params={"sender": "Acme"})).json()
    assert any(abs(float(i["amount"]) - 1250.0) < 0.01 for i in listed)
