"""Startup checks against the mock company app."""

from __future__ import annotations

import httpx

from agent.config import Settings


async def check_mock_app(settings: Settings, *, timeout: float = 2.0) -> None:
    """Raise RuntimeError with a clear message if the mock app is unreachable."""
    url = f"{settings.base_url}/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Mock app unreachable at {settings.base_url} ({exc}). "
            "Start it with `make mock` or use `make demo` / `make secondary` "
            "(those boot the server for you)."
        ) from exc
    if resp.status_code != 200:
        raise RuntimeError(
            f"Mock app health check failed ({resp.status_code}) at {url}."
        )
