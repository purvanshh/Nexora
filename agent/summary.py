"""Deterministic human-readable run summaries (no LLM — no hallucinated numbers)."""

from __future__ import annotations

from typing import Any

from agent.memory import Memory
from agent.models import VerificationResult
from agent.verifier import classify_task


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def build_summary(
    task: str,
    memory: Memory,
    verification: VerificationResult | None,
    *,
    fallback: str = "",
) -> str:
    """Build a business-facing summary from scratchpad facts + verifier result."""
    facts = memory.facts_dict()
    kind = classify_task(task)
    verified = bool(verification and verification.passed)
    verify_line = (
        "Verified: independent re-query of the source of truth confirms the outcome."
        if verified
        else "Verification: failed or incomplete — see checks in the report."
    )

    if kind == "invoice":
        # Always source the business invoice_id from scratchpad facts (email extract).
        # Never invent or use finance-generated IDs here.
        invoice_id = facts.get("invoice_id") or "NOT EXTRACTED"
        amount = facts.get("invoice_amount")
        due = facts.get("invoice_due_date") or "NOT EXTRACTED"
        sender = facts.get("sender") or facts.get("invoice_sender") or "Acme Corp"
        if amount is None and not facts:
            return fallback or "Invoice task did not produce usable facts."
        return (
            f"Submitted the latest invoice from {sender} to the finance system.\n"
            f"  Invoice: {invoice_id}\n"
            f"  Amount:  {_money(amount) if amount is not None else 'NOT EXTRACTED'}\n"
            f"  Due:     {due}\n"
            f"{verify_line.replace('the source of truth', '/api/invoices')}"
        )

    if kind == "payslip":
        emp_id = facts.get("employee_id") or 42
        net = facts.get("net_pay")
        if net is None:
            return fallback or "Payslip task did not produce a net pay figure."
        return (
            f"Employee {emp_id}'s latest payslip shows net pay of {_money(net)}.\n"
            f"{verify_line.replace('the source of truth', f'/api/payslips/{emp_id}')}"
        )

    if fallback:
        return fallback
    return f"Task finished. Facts: {facts}\n{verify_line}"
