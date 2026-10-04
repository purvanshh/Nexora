"""Independent verification — re-derive truth; reject out-of-scope writes."""

from __future__ import annotations

from typing import Any, Literal

import httpx

from agent.config import Settings, get_settings
from agent.memory import Memory
from agent.models import VerificationResult

TaskKind = Literal["invoice", "payslip", "leave", "other"]


def classify_task(task: str) -> TaskKind:
    task_l = task.lower()
    if "leave" in task_l or "time off" in task_l or "pto" in task_l:
        return "leave"
    if "payslip" in task_l or "net pay" in task_l or (
        "employee" in task_l and "invoice" not in task_l and "leave" not in task_l
    ):
        return "payslip"
    if "invoice" in task_l or "finance" in task_l or "acme" in task_l:
        return "invoice"
    return "other"


def extract_mutations(memory: Memory) -> list[dict[str, Any]]:
    """Collect write-like tool calls from the run history."""
    mutations: list[dict[str, Any]] = []
    for step in memory.steps:
        tc = step.tool_call
        if tc is None:
            continue
        if tc.tool == "api":
            method = str(tc.args.get("method", "GET")).upper()
            path = str(tc.args.get("path", ""))
            if method in {"POST", "PUT", "PATCH", "DELETE"}:
                mutations.append(
                    {
                        "step": step.index,
                        "tool": "api",
                        "method": method,
                        "path": path,
                        "ok": bool(step.observation and step.observation.ok),
                    }
                )
        elif tc.tool == "files" and tc.args.get("action") == "write":
            mutations.append(
                {
                    "step": step.index,
                    "tool": "files",
                    "method": "WRITE",
                    "path": tc.args.get("path"),
                    "ok": bool(step.observation and step.observation.ok),
                }
            )
        elif tc.tool == "browser" and tc.args.get("action") in {"fill", "click"}:
            # Treat interactive UI mutations as writes for scope analysis.
            mutations.append(
                {
                    "step": step.index,
                    "tool": "browser",
                    "method": str(tc.args.get("action")).upper(),
                    "path": tc.args.get("selector") or tc.args.get("url"),
                    "ok": bool(step.observation and step.observation.ok),
                }
            )
    return mutations


def scope_allows(kind: TaskKind, mutations: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """Return (ok, violation reasons)."""
    violations: list[str] = []
    if kind == "payslip":
        for m in mutations:
            if m["tool"] == "api" and m["method"] != "GET":
                violations.append(
                    f"scope_violation: {m['method']} {m['path']} not allowed for read-only task"
                )
            elif m["tool"] == "files":
                violations.append(f"scope_violation: file write {m['path']} not allowed")
            elif m["tool"] == "browser" and m["method"] in {"FILL", "CLICK"}:
                # Read-only payslip should not submit forms.
                violations.append(
                    f"scope_violation: browser {m['method']} not allowed for read-only task"
                )
    elif kind == "invoice":
        for m in mutations:
            if m["tool"] == "api":
                path = str(m.get("path") or "")
                if m["method"] == "POST" and "/api/invoices" in path:
                    continue
                if m["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
                    violations.append(
                        f"scope_violation: unexpected {m['method']} {path}"
                    )
            elif m["tool"] == "files":
                violations.append(f"scope_violation: unexpected file write {m['path']}")
    elif kind == "leave":
        for m in mutations:
            if m["tool"] == "api":
                path = str(m.get("path") or "")
                if m["method"] == "POST" and "/api/leave" in path:
                    continue
                if m["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
                    violations.append(
                        f"scope_violation: unexpected {m['method']} {path}"
                    )
            elif m["tool"] == "files":
                violations.append(f"scope_violation: unexpected file write {m['path']}")
    return (len(violations) == 0, violations)


class Verifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def verify(self, task: str, memory: Memory, summary: str = "") -> VerificationResult:
        kind = classify_task(task)
        mutations = extract_mutations(memory)
        scope_ok, violations = scope_allows(kind, mutations)
        checks: list[str] = [
            f"no_out_of_scope_writes: {'passed' if scope_ok else 'failed'}",
        ]
        details: dict[str, Any] = {
            "task": task,
            "task_kind": kind,
            "summary": summary,
            "facts": memory.facts_dict(),
            "mutations": mutations,
            "scope_violations": violations,
        }

        if not scope_ok:
            checks.extend(violations)
            return VerificationResult(
                passed=False,
                checks=checks,
                details=details,
                method="scope_check+api_requery",
            )

        if kind == "payslip":
            outcome = await self._verify_payslip(task, memory, details, checks)
        elif kind == "invoice":
            outcome = await self._verify_invoice(task, memory, details, checks)
        elif kind == "leave":
            outcome = await self._verify_leave(task, memory, details, checks)
        else:
            checks.append("Unknown task kind; skipped deep verification")
            outcome = VerificationResult(
                passed=False,
                checks=checks,
                details=details,
                method="api_requery",
            )
        return outcome

    async def _verify_invoice(
        self,
        task: str,
        memory: Memory,
        details: dict[str, Any],
        checks: list[str],
    ) -> VerificationResult:
        facts = memory.facts_dict()
        claimed_amount = facts.get("invoice_amount")
        claimed_due = facts.get("invoice_due_date")

        async with httpx.AsyncClient(base_url=self.settings.base_url, timeout=15.0) as client:
            # 1) Independently derive the latest Acme invoice from mail.
            checks.append("GET /api/mail?sender=Acme Corp (independent ground truth)")
            mail_resp = await client.get("/api/mail", params={"sender": "Acme Corp"})
            details["mail"] = {"status": mail_resp.status_code, "body": _safe_json(mail_resp)}
            if mail_resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Mail ground-truth query failed"],
                    details=details,
                    method="api_requery",
                )
            emails = mail_resp.json()
            ground = None
            for email in emails:  # already newest-first
                if email.get("malformed"):
                    continue
                if email.get("amount") is None:
                    continue
                ground = email
                break
            details["ground_truth_mail"] = ground
            if ground is None:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["No valid Acme invoice email found"],
                    details=details,
                    method="api_requery",
                )

            gt_amount = ground.get("amount")
            gt_due = ground.get("due_date")
            gt_invoice_id = ground.get("invoice_id")
            claimed_invoice_id = facts.get("invoice_id")
            checks.append(
                f"Derived latest Acme invoice {gt_invoice_id} "
                f"amount={gt_amount} due={gt_due}"
            )

            # 2) Confirm finance state matches ground truth (prefer lookup by source ID).
            match = None
            if gt_invoice_id:
                checks.append(f"GET /api/invoices/{gt_invoice_id}")
                by_id = await client.get(f"/api/invoices/{gt_invoice_id}")
                details["finance_by_id"] = {
                    "status": by_id.status_code,
                    "body": _safe_json(by_id),
                }
                if by_id.status_code == 200:
                    match = by_id.json()

            if match is None:
                checks.append("GET /api/invoices?sender=Acme")
                inv_resp = await client.get("/api/invoices", params={"sender": "Acme"})
                details["finance_list"] = {
                    "status": inv_resp.status_code,
                    "body": _safe_json(inv_resp),
                }
                if inv_resp.status_code != 200:
                    return VerificationResult(
                        passed=False,
                        checks=checks + ["Finance list query failed"],
                        details=details,
                        method="api_requery",
                    )
                invoices = inv_resp.json()
                for inv in invoices:
                    if _amounts_match(inv.get("amount"), gt_amount) and str(
                        inv.get("due_date")
                    ) == str(gt_due):
                        match = inv
                        break

            details["finance_match"] = match
            checks.append(
                "Finance record matches independently derived amount/due_date"
                if match
                else "No finance record matching ground-truth amount/due_date"
            )

            # 3) invoice_id must match the source email (load-bearing check).
            id_ok = False
            if match is None or not gt_invoice_id:
                checks.append("invoice_id check skipped — missing finance record or ground truth")
            elif str(match.get("invoice_id")) != str(gt_invoice_id):
                checks.append(
                    f"invoice_id mismatch: finance has {match.get('invoice_id')}, "
                    f"source says {gt_invoice_id}"
                )
            else:
                id_ok = True
                checks.append("invoice_id matches source")

            claim_id_ok = claimed_invoice_id is not None and str(claimed_invoice_id) == str(
                gt_invoice_id
            )
            checks.append(
                "Agent claimed invoice_id matches source"
                if claim_id_ok
                else "Agent claimed invoice_id missing or diverges from source"
            )

            # 4) Compare agent amount/due claims to ground truth.
            claim_ok = _amounts_match(claimed_amount, gt_amount) and (
                claimed_due is None or str(claimed_due) == str(gt_due)
            )
            checks.append(
                "Agent claimed amount/due_date match ground truth"
                if claim_ok
                else "Agent claimed amount/due_date diverge from ground truth"
            )
            details["claim_vs_ground"] = {
                "claimed_amount": claimed_amount,
                "ground_amount": gt_amount,
                "claimed_due_date": claimed_due,
                "ground_due_date": gt_due,
                "claimed_invoice_id": claimed_invoice_id,
                "ground_invoice_id": gt_invoice_id,
                "finance_invoice_id": match.get("invoice_id") if match else None,
                "claim_ok": claim_ok,
                "id_ok": id_ok,
                "claim_id_ok": claim_id_ok,
            }

            passed = match is not None and claim_ok and id_ok and claim_id_ok
            return VerificationResult(
                passed=passed,
                checks=checks,
                details=details,
                method="api_requery",
            )

    async def _verify_leave(
        self,
        task: str,
        memory: Memory,
        details: dict[str, Any],
        checks: list[str],
    ) -> VerificationResult:
        emp_id, start, end, reason = _leave_expected_fields(task, memory)
        details["leave_expected"] = {
            "employee_id": emp_id,
            "start_date": start,
            "end_date": end,
            "reason": reason,
        }

        async with httpx.AsyncClient(base_url=self.settings.base_url, timeout=15.0) as client:
            if emp_id is None or start is None or end is None:
                return VerificationResult(
                    passed=False,
                    checks=checks
                    + ["Missing employee_id/start_date/end_date for leave verification"],
                    details=details,
                    method="api_requery",
                )
            checks.append(f"GET /api/leave?employee_id={emp_id}")
            resp = await client.get("/api/leave", params={"employee_id": int(emp_id)})
            details["leave_list"] = {"status": resp.status_code, "body": _safe_json(resp)}
            if resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Leave list query failed"],
                    details=details,
                    method="api_requery",
                )
            matches = [
                item
                for item in resp.json()
                if str(item.get("start_date")) == str(start)
                and str(item.get("end_date")) == str(end)
                and (reason is None or str(item.get("reason")) == str(reason))
            ]
            details["leave_matches"] = matches
            details["leave_match"] = matches[0] if len(matches) == 1 else None
            details["leave_match_count"] = len(matches)
            if len(matches) == 0:
                checks.append("No leave record matching claimed dates/reason")
                passed = False
            elif len(matches) == 1:
                checks.append("Exactly one leave record matches claimed dates/reason")
                passed = True
            else:
                checks.append(
                    f"Leave duplicate: expected exactly 1 matching record, found {len(matches)}"
                )
                passed = False
            return VerificationResult(
                passed=passed,
                checks=checks,
                details=details,
                method="api_requery",
            )

    async def _verify_payslip(
        self,
        task: str,
        memory: Memory,
        details: dict[str, Any],
        checks: list[str],
    ) -> VerificationResult:
        facts = memory.facts_dict()
        # Derive employee id from task text when possible.
        emp_id = _employee_id_from_task(task) or facts.get("employee_id") or 42
        claimed_net = facts.get("net_pay")

        async with httpx.AsyncClient(base_url=self.settings.base_url, timeout=15.0) as client:
            checks.append(f"GET /api/employees/{emp_id} (independent)")
            emp_resp = await client.get(f"/api/employees/{emp_id}")
            details["employee"] = {
                "status": emp_resp.status_code,
                "body": _safe_json(emp_resp),
            }
            if emp_resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Employee lookup failed"],
                    details=details,
                    method="api_requery",
                )

            checks.append(f"GET /api/payslips/{emp_id} (independent ground truth)")
            slip_resp = await client.get(f"/api/payslips/{emp_id}")
            body = _safe_json(slip_resp)
            details["payslip"] = {"status": slip_resp.status_code, "body": body}
            if slip_resp.status_code != 200:
                return VerificationResult(
                    passed=False,
                    checks=checks + ["Payslip ground-truth query failed"],
                    details=details,
                    method="api_requery",
                )

            actual_net = body.get("net_pay")
            checks.append(f"Ground-truth net_pay for employee {emp_id} is {actual_net}")
            claim_ok = claimed_net is not None and _amounts_match(actual_net, claimed_net)
            checks.append(
                "Agent claimed net_pay matches ground truth"
                if claim_ok
                else "Agent claimed net_pay missing or diverges from ground truth"
            )
            details["claim_vs_ground"] = {
                "claimed_net_pay": claimed_net,
                "ground_net_pay": actual_net,
                "employee_id": emp_id,
                "claim_ok": claim_ok,
            }
            return VerificationResult(
                passed=claim_ok,
                checks=checks,
                details=details,
                method="api_requery",
            )


def _employee_id_from_task(task: str) -> int | None:
    import re

    match = re.search(r"employee\s*(?:id\s*)?(\d+)", task.lower())
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\b", task)
    return int(match.group(1)) if match else None


def _leave_payload_from_steps(memory: Memory) -> dict[str, Any]:
    """Last successful POST /api/leave body (planner often skips remember)."""
    for step in reversed(memory.steps):
        tc = step.tool_call
        if tc is None or tc.tool != "api":
            continue
        if str(tc.args.get("method", "")).upper() != "POST":
            continue
        if "/api/leave" not in str(tc.args.get("path", "")):
            continue
        if not (step.observation and step.observation.ok):
            continue
        body = tc.args.get("json") or tc.args.get("json_body") or {}
        if isinstance(body, dict):
            return body
    return {}


def _leave_dates_from_task(task: str) -> tuple[str | None, str | None, str | None]:
    import re

    dates = re.findall(r"\d{4}-\d{2}-\d{2}", task)
    start = dates[0] if len(dates) >= 1 else None
    end = dates[1] if len(dates) >= 2 else None
    reason = None
    m = re.search(r"reason\s+([A-Za-z0-9 _-]+)", task, flags=re.IGNORECASE)
    if m:
        reason = m.group(1).strip().rstrip(".")
    return start, end, reason


def _leave_expected_fields(
    task: str, memory: Memory
) -> tuple[Any, Any, Any, Any]:
    """Resolve leave fields from facts, then POST body, then task text."""
    facts = memory.facts_dict()
    payload = _leave_payload_from_steps(memory)
    task_start, task_end, task_reason = _leave_dates_from_task(task)
    emp_id = (
        _employee_id_from_task(task)
        or facts.get("employee_id")
        or payload.get("employee_id")
    )
    start = (
        facts.get("leave_start")
        or facts.get("start_date")
        or payload.get("start_date")
        or task_start
    )
    end = (
        facts.get("leave_end")
        or facts.get("end_date")
        or payload.get("end_date")
        or task_end
    )
    reason = (
        facts.get("leave_reason")
        or facts.get("reason")
        or payload.get("reason")
        or task_reason
    )
    return emp_id, start, end, reason


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
