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
    assert len(obs.data["body"]) == 6  # includes Acme Corporation decoy


@pytest.mark.asyncio
async def test_api_404_observation(mock_app: str) -> None:
    tool = APITool(mock_app)
    obs = await tool.run(APIArgs(method="GET", path="/api/mail/does-not-exist"))
    assert not obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 404


@pytest.mark.asyncio
async def test_api_422_includes_validation_detail(mock_app: str) -> None:
    """Missing required fields must surface FastAPI detail to the planner."""
    tool = APITool(mock_app)
    obs = await tool.run(
        APIArgs(
            method="POST",
            path="/api/invoices",
            json={
                "invoice_id": "INV-4471",
                "amount": 1250,
                "due_date": "2025-03-15",
                # sender intentionally omitted
            },
        )
    )
    assert not obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 422
    assert obs.data.get("retryable") is False
    assert obs.error is not None
    assert "sender" in obs.error.lower() or "sender" in str(obs.data.get("body")).lower()


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


@pytest.mark.asyncio
async def test_create_invoice_honors_client_invoice_id(mock_app: str) -> None:
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
    assert obs.data["body"]["invoice_id"] == "INV-4471"

    dup = await tool.run(
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
    assert not dup.ok
    assert dup.data is not None
    assert dup.data["status_code"] == 409


@pytest.mark.asyncio
async def test_chaos_first_post_500_then_201(mock_app: str, monkeypatch) -> None:
    """CHAOS=1 must inject a 500 on the first invoice POST, then allow retry."""
    import os

    from mock_app.routers.finance import reset_chaos

    monkeypatch.setenv("CHAOS", "1")
    reset_chaos()
    # The live uvicorn process won't see monkeypatch — hit the app via TestClient-style
    # by calling the route logic through httpx only works if server has CHAOS.
    # Restart is heavy; instead unit-test the handler env read via direct ASGI transport.
    from httpx import ASGITransport, AsyncClient

    from mock_app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reset_chaos()
        os.environ["CHAOS"] = "1"
        first = await client.post(
            "/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 1250.0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-4471",
            },
        )
        assert first.status_code == 500
        assert first.json().get("chaos") is True
        second = await client.post(
            "/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 1250.0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-4471",
            },
        )
        assert second.status_code == 201
    monkeypatch.delenv("CHAOS", raising=False)
    reset_chaos()
