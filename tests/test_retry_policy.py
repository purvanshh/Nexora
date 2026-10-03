"""Retry policy: 4xx is semantic (no retry); 5xx is transient."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agent.loop import execute_with_retry, is_retryable
from agent.models import Observation, ToolCall
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry


def test_is_retryable_distinguishes_status_classes() -> None:
    assert is_retryable(Observation(ok=False, data={"status_code": 500}, error="HTTP 500"))
    assert is_retryable(Observation(ok=False, data={"status_code": 503}, error="HTTP 503"))
    assert not is_retryable(
        Observation(ok=False, data={"status_code": 422}, error="HTTP 422: missing sender")
    )
    assert not is_retryable(Observation(ok=False, data={"status_code": 409}, error="HTTP 409"))
    assert is_retryable(Observation(ok=False, error="All connection attempts failed"))


class _Args(BaseModel):
    x: int = 1


class _Always422(Tool):
    name = "api"
    description = "returns 422"
    args_schema = _Args

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, args: BaseModel) -> Observation:
        self.calls += 1
        return Observation(
            ok=False,
            error="HTTP 422: [{'loc': ['body', 'sender'], 'msg': 'Field required'}]",
            data={
                "status_code": 422,
                "body": {"detail": [{"loc": ["body", "sender"], "msg": "Field required"}]},
            },
        )


@pytest.mark.asyncio
async def test_execute_with_retry_does_not_repeat_422() -> None:
    tool = _Always422()
    registry = ToolRegistry()
    registry.register(tool)
    obs = await execute_with_retry(
        registry,
        ToolCall(tool="api", args={"x": 1}),
        retries=2,
    )
    assert not obs.ok
    assert obs.data is not None
    assert obs.data["status_code"] == 422
    assert tool.calls == 1


class _Flaky500ThenOk(Tool):
    name = "api"
    description = "500 then 200"
    args_schema = _Args

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, args: BaseModel) -> Observation:
        self.calls += 1
        if self.calls == 1:
            return Observation(
                ok=False,
                error="HTTP 500",
                data={"status_code": 500, "body": {"detail": "boom"}},
            )
        return Observation(ok=True, data={"status_code": 200, "body": {"ok": True}})


@pytest.mark.asyncio
async def test_execute_with_retry_retries_500() -> None:
    tool = _Flaky500ThenOk()
    registry = ToolRegistry()
    registry.register(tool)
    obs = await execute_with_retry(
        registry,
        ToolCall(tool="api", args={"x": 1}),
        retries=2,
    )
    assert obs.ok
    assert tool.calls == 2
