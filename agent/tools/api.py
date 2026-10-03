"""HTTP tool for the mock company REST API."""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agent.models import Observation
from agent.tools.base import Tool


class APIArgs(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: str = Field(description="Path under MOCK_APP_URL, e.g. /api/mail")
    json_body: dict[str, Any] | None = Field(
        default=None,
        alias="json",
        description="JSON request body for POST/PUT/PATCH",
    )
    params: dict[str, Any] | None = None


class APITool(Tool):
    name = "api"
    description = (
        "Call the mock company REST API (mail, finance, HR). "
        "Prefer this for structured data; use browser for UI confirmation."
    )
    args_schema = APIArgs

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, APIArgs)
        started = time.perf_counter()
        url = args.path if args.path.startswith("http") else f"{self.base_url}{args.path}"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.request(
                    args.method,
                    url,
                    json=args.json_body,
                    params=args.params,
                )
            try:
                body: Any = resp.json()
            except Exception:
                body = {"text": resp.text}

            ok = 200 <= resp.status_code < 300
            error: str | None = None
            if not ok:
                # Surface validation detail so the planner can fix 4xx payloads
                # instead of blindly retrying the same body.
                detail = body.get("detail") if isinstance(body, dict) else body
                error = f"HTTP {resp.status_code}"
                if detail is not None:
                    error = f"{error}: {detail}"
            return Observation(
                ok=ok,
                data={
                    "status_code": resp.status_code,
                    "body": body,
                    "url": url,
                    "method": args.method,
                    "retryable": 500 <= resp.status_code < 600,
                },
                error=error,
                duration_ms=int((time.perf_counter() - started) * 1000),
                evidence=[url],
            )
        except Exception as exc:  # noqa: BLE001
            return Observation(
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
