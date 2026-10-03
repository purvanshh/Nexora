"""FastAPI entrypoint: web UI + REST for the simulated company."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles

from mock_app.routers import finance, hr, mail
from mock_app.routers.finance import reset_chaos
from mock_app.store import reset_data

app = FastAPI(title="Nexora Mock Company App", version="0.1.0")

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(mail.router)
app.include_router(finance.router)
app.include_router(hr.router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "nexora-mock-app",
        "health": "/health",
        "mail": "/mail",
        "finance": "/finance",
        "api_mail": "/api/mail",
        "api_invoices": "/api/invoices",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Silence browser favicon noise in access logs."""
    return Response(status_code=204)


@app.post("/api/reset")
async def api_reset() -> dict[str, str]:
    reset_data()
    reset_chaos()
    return {"status": "reset"}
