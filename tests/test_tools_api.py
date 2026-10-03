"""APITool tests against the live mock app."""

from __future__ import annotations

import pytest

from agent.tools.api import APIArgs, APITool


@pytest.mark.asyncio
async def test_api_list_mail_200(mock_app: str) -> None:
    tool = APITool(mock_app)
    obs = await tool.run(APIArgs(method="GET", path="/api/mail"))
    assert obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 200
    assert isinstance(obs.data["body"], list)
    assert len(obs.data["body"]) == 5


@pytest.mark.asyncio
async def test_api_404_observation(mock_app: str) -> None:
    tool = APITool(mock_app)
    obs = await tool.run(APIArgs(method="GET", path="/api/mail/does-not-exist"))
    assert not obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 404


@pytest.mark.asyncio
async def test_api_reject_non_positive_amount(mock_app: str) -> None:
    tool = APITool(mock_app)
    obs = await tool.run(
        APIArgs(
            method="POST",
            path="/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-0",
            },
        )
    )
    assert not obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 400


@pytest.mark.asyncio
async def test_api_create_invoice_201(mock_app: str) -> None:
    tool = APITool(mock_app)
    obs = await tool.run(
        APIArgs(
            method="POST",
            path="/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 1250.0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-4471",
            },
        )
    )
    assert obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 201
    assert obs.data["body"]["amount"] == 1250.0
