"""HR employee + payslip + leave routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mock_app.store import read_json, write_json

router = APIRouter()


class LeaveCreate(BaseModel):
    employee_id: int
    start_date: str
    end_date: str
    reason: str = Field(min_length=1)


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


@router.get("/api/leave")
async def list_leave(employee_id: int | None = None) -> list[dict[str, Any]]:
    items = read_json("leave_requests.json")
    if employee_id is not None:
        items = [i for i in items if int(i.get("employee_id", -1)) == employee_id]
    return items


@router.get("/api/leave/{leave_id}")
async def get_leave(leave_id: str) -> dict[str, Any]:
    items = read_json("leave_requests.json")
    for item in items:
        if item.get("id") == leave_id:
            return item
    raise HTTPException(status_code=404, detail="Leave request not found")


@router.post("/api/leave")
async def create_leave(payload: LeaveCreate) -> dict[str, Any]:
    employees = read_json("employees.json")
    if not any(int(e["id"]) == payload.employee_id for e in employees):
        raise HTTPException(status_code=404, detail="Employee not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on/after start_date")

    record = {
        "id": f"leave-{uuid.uuid4().hex[:8]}",
        "employee_id": payload.employee_id,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "reason": payload.reason,
        "status": "submitted",
    }
    items = read_json("leave_requests.json")
    items.append(record)
    write_json("leave_requests.json", items)
    return record
