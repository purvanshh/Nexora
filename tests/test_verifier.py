"""Verifier independent re-query tests."""

from __future__ import annotations

import httpx
import pytest

from agent.config import Settings
from agent.memory import Memory
from agent.verifier import Verifier


@pytest.mark.asyncio
async def test_verifier_fails_when_finance_empty(mock_app: str, workspace, tmp_path) -> None:
    settings = Settings(
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
    )
    mem = Memory(task="enter Acme invoice")
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
        body = resp.json()

    settings = Settings(
        mock_app_url=mock_app,
        workspace_dir=workspace,
        trace_dir=tmp_path / "traces",
    )
    mem = Memory(task="enter Acme invoice")
    mem.remember("invoice_amount", 1250.0, 0)
    mem.remember("invoice_due_date", "2025-03-15", 0)
    mem.remember("sender", "Acme Corp", 0)
    mem.remember("invoice_id", body["id"], 1)
    result = await Verifier(settings).verify(mem.task, mem, summary="submitted")
    assert result.passed is True
    assert result.method == "api_requery"
