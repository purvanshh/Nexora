"""Verifier independent re-query + scope tests."""

from __future__ import annotations

import httpx
import pytest

from agent.config import Settings
from agent.memory import Memory
from agent.models import Observation, ToolCall
from agent.verifier import Verifier, extract_mutations, scope_allows


@pytest.mark.asyncio
async def test_verifier_fails_when_finance_empty(mock_app: str, workspace, tmp_path) -> None:
    settings = Settings(
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
    )
    mem = Memory(
        task=(
            "Find the latest invoice from Acme Corp, extract amount and due date, "
            "enter it into the finance system."
        )
    )
    mem.remember("invoice_amount", 1250.0, 0)
    mem.remember("invoice_due_date", "2025-03-15", 0)
    mem.remember("sender", "Acme Corp", 0)
    result = await Verifier(settings).verify(mem.task, mem, summary="done")
    assert result.passed is False


@pytest.mark.asyncio
async def test_verifier_passes_when_record_exists(mock_app: str, workspace, tmp_path) -> None:
    async with httpx.AsyncClient(base_url=mock_app) as client:
        resp = await client.post(
            "/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 1250.0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-4471",
            },
        )
        assert resp.status_code == 201

    settings = Settings(
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
    )
    mem = Memory(
        task=(
            "Find the latest invoice from Acme Corp, extract amount and due date, "
            "enter it into the finance system."
        )
    )
    mem.add_step(
        0,
        "submit",
        ToolCall(
            tool="api",
            args={
                "method": "POST",
                "path": "/api/invoices",
                "json": {
                    "sender": "Acme Corp",
                    "amount": 1250.0,
                    "due_date": "2025-03-15",
                },
            },
        ),
        Observation(ok=True, data={"status_code": 201}),
    )
    mem.remember("invoice_amount", 1250.0, 1)
    mem.remember("invoice_due_date", "2025-03-15", 1)
    mem.remember("sender", "Acme Corp", 1)
    result = await Verifier(settings).verify(mem.task, mem, summary="submitted")
    assert result.passed is True
    assert "no_out_of_scope_writes: passed" in result.checks


@pytest.mark.asyncio
async def test_verifier_rejects_extra_write(mock_app: str, workspace, tmp_path) -> None:
    """Payslip task must fail verification if the agent POSTed an invoice."""
    settings = Settings(
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
    )
    mem = Memory(
        task="Look up employee 42, get their latest payslip, and tell me their net pay."
    )
    mem.add_step(
        0,
        "read payslip",
        ToolCall(tool="api", args={"method": "GET", "path": "/api/payslips/42"}),
        Observation(ok=True, data={"status_code": 200, "body": {"net_pay": 5412.8}}),
    )
    mem.remember("employee_id", 42, 0)
    mem.remember("net_pay", 5412.8, 0)
    # Out-of-scope side effect
    mem.add_step(
        1,
        "oops create invoice",
        ToolCall(
            tool="api",
            args={
                "method": "POST",
                "path": "/api/invoices",
                "json": {"sender": "Acme Corp", "amount": 1, "due_date": "2025-01-01"},
            },
        ),
        Observation(ok=True, data={"status_code": 201}),
    )

    result = await Verifier(settings).verify(mem.task, mem, summary="net pay is 5412.8")
    assert result.passed is False
    assert "no_out_of_scope_writes: failed" in result.checks
    assert any("scope_violation" in c for c in result.checks)
    assert result.details.get("scope_violations")


def test_extract_mutations_and_scope_helpers() -> None:
    mem = Memory(task="payslip")
    mem.add_step(
        0,
        "bad",
        ToolCall(tool="api", args={"method": "POST", "path": "/api/invoices"}),
        Observation(ok=True),
    )
    mutations = extract_mutations(mem)
    ok, violations = scope_allows("payslip", mutations)
    assert ok is False
    assert violations
