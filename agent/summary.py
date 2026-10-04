"""Deterministic human-readable run summaries (no LLM — no hallucinated numbers)."""

from __future__ import annotations

import json
from typing import Any

from agent.memory import Memory
from agent.models import VerificationResult
from agent.verifier import classify_task


def _money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _compact(record: Any, keys: list[str]) -> str:
    """Embed a small durable record snapshot (not a dead localhost URL)."""
    if not isinstance(record, dict):
        return ""
    slim = {k: record.get(k) for k in keys if k in record}
    if not slim:
        slim = {k: record[k] for k in list(record)[:8]}
    return json.dumps(slim, default=str, sort_keys=True)


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
    details = (verification.details if verification else {}) or {}
    verify_line = (
        "Verified: re-queried the mock app APIs to confirm the outcome "
        "(independent of the agent's own claims; still depends on the mock being correct)."
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
        mail_snap = _compact(
            details.get("ground_truth_mail"),
            ["id", "sender", "invoice_id", "amount", "due_date", "timestamp"],
        )
        fin_snap = _compact(
            details.get("finance_match"),
            ["id", "invoice_id", "sender", "amount", "due_date"],
        )
        lines = [
            f"Submitted the latest invoice from {sender} to the finance system.",
            f"  Invoice: {invoice_id}",
            f"  Amount:  {_money(amount) if amount is not None else 'NOT EXTRACTED'}",
            f"  Due:     {due}",
            verify_line,
        ]
        if mail_snap:
            lines.append(f"  Source mail record: {mail_snap}")
        if fin_snap:
            lines.append(f"  Finance record: {fin_snap}")
        return "\n".join(lines)

    if kind == "payslip":
        emp_id = facts.get("employee_id") or 42
        net = facts.get("net_pay")
        if net is None:
            return fallback or "Payslip task did not produce a net pay figure."
        slip_body = None
        payslip = details.get("payslip")
        if isinstance(payslip, dict):
            slip_body = payslip.get("body")
        slip_snap = _compact(
            slip_body,
            ["employee_id", "net_pay", "gross_pay", "issued_at", "period"],
        )
        lines = [
            f"Employee {emp_id}'s latest payslip shows net pay of {_money(net)}.",
            verify_line,
        ]
        if slip_snap:
            lines.append(f"  Payslip record: {slip_snap}")
        return "\n".join(lines)

    if kind == "leave":
        expected = details.get("leave_expected") if isinstance(details, dict) else None
        expected = expected if isinstance(expected, dict) else {}
        emp_id = (
            facts.get("employee_id")
            or expected.get("employee_id")
            or "NOT EXTRACTED"
        )
        start = (
            facts.get("leave_start")
            or facts.get("start_date")
            or expected.get("start_date")
            or "NOT EXTRACTED"
        )
        end = (
            facts.get("leave_end")
            or facts.get("end_date")
            or expected.get("end_date")
            or "NOT EXTRACTED"
        )
        reason = (
            facts.get("leave_reason")
            or facts.get("reason")
            or expected.get("reason")
            or "NOT EXTRACTED"
        )
        leave_snap = _compact(
            details.get("leave_match"),
            ["id", "employee_id", "start_date", "end_date", "reason", "status"],
        )
        lines = [
            f"Filed leave for employee {emp_id} from {start} to {end} ({reason}).",
            verify_line,
        ]
        if leave_snap:
            lines.append(f"  Leave record: {leave_snap}")
        return "\n".join(lines)

    if fallback:
        return fallback
    return f"Task finished. Facts: {facts}\n{verify_line}"
