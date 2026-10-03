"""Independent verification — never trust the executor's claim alone."""

from __future__ import annotations

from typing import Any

import httpx

from agent.config import Settings, get_settings
from agent.memory import Memory
from agent.models import VerificationResult


class Verifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def verify(self, task: str, memory: Memory, summary: str = "") -> VerificationResult:
        facts = memory.facts_dict()
        task_l = task.lower()

        if "payslip" in task_l or "employee" in task_l or "net pay" in task_l:
            return await self._verify_payslip(facts, task, summary)

        return await self._verify_invoice(facts, task, summary)

    async def _verify_invoice(
        self,
        facts: dict[str, Any],
        task: str,
        summary: str,
    ) -> VerificationResult:
        checks: list[str] = []
        details: dict[str, Any] = {"task": task, "summary": summary, "facts": facts}
        amount = facts.get("invoice_amount")
        due_date = facts.get("invoice_due_date")
        sender = facts.get("sender") or facts.get("invoice_sender") or "Acme Corp"
        invoice_id = facts.get("invoice_id") or facts.get("finance_invoice_id")

        async with httpx.AsyncClient(base_url=self.settings.base_url, timeout=15.0) as client:
            if invoice_id:
                checks.append(f"GET /api/invoices/{invoice_id}")
                resp = await client.get(f"/api/invoices/{invoice_id}")
                details["by_id"] = {"status": resp.status_code, "body": _safe_json(resp)}
                if resp.status_code == 200:
                    body = resp.json()
                    passed = _amounts_match(body.get("amount"), amount) and (
                        due_date is None or str(body.get("due_date")) == str(due_date)
                    )
                    checks.append("Compared amount and due_date against scratchpad facts")
                    details["comparison"] = {
                        "expected_amount": amount,
                        "actual_amount": body.get("amount"),
                        "expected_due_date": due_date,
                        "actual_due_date": body.get("due_date"),
                    }
                    return VerificationResult(
                        passed=passed,
                        checks=checks,
                        details=details,
                        method="api_requery",
                    )

            checks.append(f"GET /api/invoices?sender={sender}")
            resp = await client.get("/api/invoices", params={"sender": sender})
            details["list"] = {"status": resp.status_code, "body": _safe_json(resp)}
            if resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Finance list endpoint failed"],
                    details=details,
                    method="api_requery",
                )

            invoices = resp.json()
            if not isinstance(invoices, list):
                invoices = invoices.get("items", [])

            match = None
            for inv in invoices:
                if _amounts_match(inv.get("amount"), amount) and (
                    due_date is None or str(inv.get("due_date")) == str(due_date)
                ):
                    match = inv
                    break

            checks.append("Searched finance records for matching amount/due_date")
            details["match"] = match
            return VerificationResult(
                passed=match is not None,
                checks=checks,
                details=details,
                method="api_requery",
            )

    async def _verify_payslip(
        self,
        facts: dict[str, Any],
        task: str,
        summary: str,
    ) -> VerificationResult:
        checks: list[str] = []
        details: dict[str, Any] = {"task": task, "summary": summary, "facts": facts}
        emp_id = facts.get("employee_id") or 42
        claimed_net = facts.get("net_pay")

        async with httpx.AsyncClient(base_url=self.settings.base_url, timeout=15.0) as client:
            checks.append(f"GET /api/payslips/{emp_id}")
            resp = await client.get(f"/api/payslips/{emp_id}")
            body = _safe_json(resp)
            details["payslip"] = {"status": resp.status_code, "body": body}
            if resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Payslip endpoint failed"],
                    details=details,
                    method="api_requery",
                )
            actual_net = body.get("net_pay")
            checks.append("Compared claimed net_pay against API payslip")
            details["comparison"] = {
                "claimed_net_pay": claimed_net,
                "actual_net_pay": actual_net,
            }
            passed = claimed_net is not None and _amounts_match(actual_net, claimed_net)
            return VerificationResult(
                passed=passed,
                checks=checks,
                details=details,
                method="api_requery",
            )


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"text": resp.text}


def _amounts_match(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < 0.005
    except (TypeError, ValueError):
        return str(a) == str(b)
