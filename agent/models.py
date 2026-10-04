"""Pydantic contracts shared across agent layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class Observation(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int = 0
    evidence: list[str] = Field(default_factory=list)


class Step(BaseModel):
    index: int
    tool_call: ToolCall | None = None
    observation: Observation | None = None
    thought: str = ""


class Fact(BaseModel):
    key: str
    value: Any
    source_step: int


class VerificationResult(BaseModel):
    passed: bool
    checks: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    method: str = "api_requery"


class RunResult(BaseModel):
    task: str
    status: Literal["success", "partial", "failed"]
    steps: list[Step] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    verification: VerificationResult | None = None
    summary: str = ""
    evidence_paths: list[str] = Field(default_factory=list)
    started_at: datetime
    ended_at: datetime
    user_aborted: bool = False
    """True when the human chose abort after escalation (expected failure path)."""


class LLMResponse(BaseModel):
    """Parsed planner output: either a tool call or a finish signal."""

    thought: str = ""
    is_finish: bool = False
    tool_call: ToolCall | None = None
    summary: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


class RememberArgs(BaseModel):
    key: str
    value: Any


class FinishArgs(BaseModel):
    summary: str
