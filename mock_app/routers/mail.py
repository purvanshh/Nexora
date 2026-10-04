"""Mail inbox routes (HTML + JSON)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from mock_app.store import read_json

router = APIRouter()
_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES))


def _emails_sorted() -> list[dict]:
    emails = read_json("emails.json")
    return sorted(emails, key=lambda e: e["timestamp"], reverse=True)


@router.get("/mail", response_class=HTMLResponse)
async def inbox_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "inbox.html",
        {"emails": _emails_sorted()},
    )


@router.get("/mail/{mail_id}", response_class=HTMLResponse)
async def email_page(request: Request, mail_id: str) -> HTMLResponse:
    for email in _emails_sorted():
        if email["id"] == mail_id:
            return templates.TemplateResponse(
                request,
                "email.html",
                {"email": email},
            )
    raise HTTPException(status_code=404, detail="Email not found")


@router.get("/api/mail")
async def list_mail(sender: str | None = None) -> list[dict]:
    emails = _emails_sorted()
    if sender:
        # Exact match (case-insensitive). Substring would collapse "Acme Corp"
        # into the "Acme Corporation" decoy and hide the latest-invoice test.
        sender_l = sender.lower().strip()
        emails = [e for e in emails if str(e.get("sender", "")).lower().strip() == sender_l]
    return emails


@router.get("/api/mail/{mail_id}")
async def get_mail(mail_id: str) -> dict:
    for email in _emails_sorted():
        if email["id"] == mail_id:
            return email
    raise HTTPException(status_code=404, detail="Email not found")
