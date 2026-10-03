"""Finance invoice routes (HTML + JSON) with optional chaos injection."""

from __future__ import annotations

import os
import uuid
from typing import Any

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from mock_app.store import read_json, write_json

router = APIRouter()
_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES))

# Chaos: fail the first POST when CHAOS=1
_chaos_posts = 0


class InvoiceCreate(BaseModel):
    sender: str
    amount: float
    due_date: str
    invoice_id: str | None = None
    source_mail_id: str | None = None
    notes: str | None = None


@router.get("/finance", response_class=HTMLResponse)
async def finance_form(request: Request) -> HTMLResponse:
    invoices = read_json("invoices.json")
    return templates.TemplateResponse(
        request,
        "finance_form.html",
        {"invoices": invoices},
    )


@router.get("/finance/invoices", response_class=HTMLResponse)
async def invoice_list_page(request: Request) -> HTMLResponse:
    invoices = read_json("invoices.json")
    return templates.TemplateResponse(
        request,
        "invoice_list.html",
        {"invoices": invoices},
    )


@router.get("/api/invoices")
async def list_invoices(sender: str | None = None) -> list[dict[str, Any]]:
    invoices = read_json("invoices.json")
    if sender:
        sender_l = sender.lower()
        invoices = [i for i in invoices if sender_l in str(i.get("sender", "")).lower()]
    return invoices


@router.get("/api/invoices/{invoice_id}")
async def get_invoice(invoice_id: str) -> dict[str, Any]:
    invoices = read_json("invoices.json")
    for inv in invoices:
        if inv["id"] == invoice_id or inv.get("invoice_id") == invoice_id:
            return inv
    raise HTTPException(status_code=404, detail="Invoice not found")


@router.post("/api/invoices")
async def create_invoice(payload: InvoiceCreate) -> JSONResponse:
    global _chaos_posts
    if os.getenv("CHAOS", "0") == "1" and _chaos_posts == 0:
        _chaos_posts += 1
        return JSONResponse(
            status_code=500,
            content={"detail": "Injected chaos failure on first POST"},
        )

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than 0")

    invoices = read_json("invoices.json")
    record = {
        "id": f"fin-{uuid.uuid4().hex[:8]}",
        "invoice_id": payload.invoice_id or f"INV-{uuid.uuid4().hex[:4].upper()}",
        "sender": payload.sender,
        "amount": payload.amount,
        "due_date": payload.due_date,
        "source_mail_id": payload.source_mail_id,
        "notes": payload.notes,
    }
    invoices.append(record)
    write_json("invoices.json", invoices)
    return JSONResponse(status_code=201, content=record)


@router.post("/finance/submit", response_class=HTMLResponse)
async def submit_form(request: Request) -> HTMLResponse:
    """HTML form POST handler (application/x-www-form-urlencoded)."""
    form = await request.form()
    try:
        amount = float(str(form.get("amount", "0")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid amount") from exc
    due_date = str(form.get("due_date", ""))
    invoice_id = str(form.get("invoice_id") or "") or None
    sender_val = str(form.get("sender", ""))

    if amount <= 0:
        return templates.TemplateResponse(
            request,
            "finance_form.html",
            {
                "invoices": read_json("invoices.json"),
                "error": "Amount must be greater than 0",
            },
            status_code=400,
        )

    create = InvoiceCreate(
        sender=sender_val,
        amount=amount,
        due_date=due_date,
        invoice_id=invoice_id,
    )
    # Reuse API logic without chaos for form path? Keep chaos for API only.
    invoices = read_json("invoices.json")
    record = {
        "id": f"fin-{uuid.uuid4().hex[:8]}",
        "invoice_id": create.invoice_id or f"INV-{uuid.uuid4().hex[:4].upper()}",
        "sender": create.sender,
        "amount": create.amount,
        "due_date": create.due_date,
        "source_mail_id": None,
        "notes": "submitted-via-form",
    }
    invoices.append(record)
    write_json("invoices.json", invoices)
    return templates.TemplateResponse(
        request,
        "invoice_list.html",
        {"invoices": invoices, "flash": f"Saved {record['invoice_id']}"},
    )


def reset_chaos() -> None:
    global _chaos_posts
    _chaos_posts = 0
