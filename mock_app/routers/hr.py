"""HR employee + payslip routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from mock_app.store import read_json

router = APIRouter()


@router.get("/api/employees/{emp_id}")
async def get_employee(emp_id: int) -> dict[str, Any]:
    employees = read_json("employees.json")
    for emp in employees:
        if int(emp["id"]) == emp_id:
            return emp
    raise HTTPException(status_code=404, detail="Employee not found")


@router.get("/api/payslips/{emp_id}")
async def get_latest_payslip(emp_id: int) -> dict[str, Any]:
    payslips = read_json("payslips.json")
    items = payslips.get(str(emp_id), [])
    if not items:
        raise HTTPException(status_code=404, detail="No payslips for employee")
    latest = sorted(items, key=lambda p: p["issued_at"], reverse=True)[0]
    return latest
