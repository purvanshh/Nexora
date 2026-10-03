"""Deterministic summary templates."""

from __future__ import annotations

from agent.memory import Memory
from agent.models import VerificationResult
from agent.summary import build_summary


def test_invoice_summary_template() -> None:
    mem = Memory(task="enter Acme invoice into finance")
    mem.remember("invoice_amount", 1250.0, 0)
    mem.remember("invoice_due_date", "2025-03-15", 0)
    mem.remember("invoice_id", "INV-4471", 0)
    mem.remember("sender", "Acme Corp", 0)
    text = build_summary(
        mem.task,
        mem,
        VerificationResult(passed=True, checks=["ok"], method="api_requery"),
    )
    assert "INV-4471" in text
    assert "$1,250.00" in text
    assert "2025-03-15" in text
    assert "Verified" in text
    assert "{" not in text


def test_payslip_summary_template() -> None:
    mem = Memory(task="Look up employee 42 net pay")
    mem.remember("employee_id", 42, 0)
    mem.remember("net_pay", 5412.8, 0)
    text = build_summary(
        mem.task,
        mem,
        VerificationResult(passed=True, checks=["ok"], method="api_requery"),
    )
    assert "Employee 42" in text
    assert "$5,412.80" in text
    assert "/api/payslips/42" in text
