"""POST retry safety: 409 / committed-but-500 recovers via matching GET."""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from agent.loop import execute_with_retry
from agent.models import Observation, ToolCall
from agent.tools.api import APIArgs, APITool
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_409_matching_invoice_recovers_as_success(mock_app: str) -> None:
    """Duplicate POST after a successful write should not fail the agent."""
    tool = APITool(mock_app)
    registry = ToolRegistry()
    registry.register(tool)
    payload = {
        "sender": "Acme Corp",
        "amount": 1250.0,
        "due_date": "2025-03-15",
        "invoice_id": "INV-4471",
    }
    first = await execute_with_retry(
        registry,
        ToolCall(tool="api", args={"method": "POST", "path": "/api/invoices", "json": payload}),
        retries=0,
    )
    assert first.ok

    second = await execute_with_retry(
        registry,
        ToolCall(tool="api", args={"method": "POST", "path": "/api/invoices", "json": payload}),
        retries=0,
    )
    assert second.ok
    assert second.data is not None
    assert second.data.get("idempotent_recover") is True

    async with httpx.AsyncClient(base_url=mock_app) as client:
        listed = (await client.get("/api/invoices")).json()
    assert len([i for i in listed if i.get("invoice_id") == "INV-4471"]) == 1


@pytest.mark.asyncio
async def test_recover_after_false_500_when_record_exists(mock_app: str) -> None:
    """Simulate committed write + 500 response: recover via GET before blind retry."""
    async with httpx.AsyncClient(base_url=mock_app) as client:
        r = await client.post(
            "/api/invoices",
            json={
                "sender": "Acme Corp",
                "amount": 1250.0,
                "due_date": "2025-03-15",
                "invoice_id": "INV-4471",
            },
        )
        assert r.status_code == 201

    class PostAlways500(Tool):
        name = "api"
        description = "POST looks like 500; GET is real"
        args_schema = APIArgs

        def __init__(self) -> None:
            self.post_calls = 0
            self.real = APITool(mock_app)

        async def run(self, args: BaseModel) -> Observation:
            assert isinstance(args, APIArgs)
            if args.method == "GET":
                return await self.real.run(args)
            self.post_calls += 1
            return Observation(
                ok=False,
                error="HTTP 500: fake timeout after commit",
                data={"status_code": 500, "body": {"detail": "fake"}},
            )

    tool = PostAlways500()
    registry = ToolRegistry()
    registry.register(tool)
    obs = await execute_with_retry(
        registry,
        ToolCall(
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
        retries=2,
    )
    assert obs.ok
    assert obs.data is not None
    assert obs.data.get("idempotent_recover") is True
    # Recovered after the first failed POST — no blind multi-POST storm.
    assert tool.post_calls == 1
