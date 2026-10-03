"""Structured JSONL tracing for every LLM / tool / verification event."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent.models import Observation, RunResult, ToolCall


class Tracer:
    def __init__(self, run_id: str | None = None, trace_dir: Path | None = None) -> None:
        self.run_id = run_id or uuid4().hex[:12]
        self.trace_dir = Path(trace_dir or "./traces")
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.trace_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.trace_dir / f"{self.run_id}.jsonl"
        self._fh = self.path.open("a", encoding="utf-8")

    def _emit(self, event_type: str, **payload: Any) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "type": event_type,
            "run_id": self.run_id,
            **payload,
        }
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def log_run_start(self, task: str, model: str) -> None:
        self._emit("run_start", task=task, model=model)

    def log_llm_call(
        self,
        step: int,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
    ) -> None:
        self._emit(
            "llm_call",
            step=step,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

    def log_thought(self, step: int, text: str, tool_call: ToolCall | None) -> None:
        self._emit("thought", step=step, text=text)
        if tool_call is not None:
            self._emit(
                "tool_call",
                step=step,
                tool=tool_call.tool,
                args=tool_call.args,
                reasoning=tool_call.reasoning,
            )

    def log_observation(self, step: int, obs: Observation) -> None:
        self._emit(
            "observation",
            step=step,
            ok=obs.ok,
            data=obs.data,
            error=obs.error,
            duration_ms=obs.duration_ms,
            evidence=obs.evidence,
        )

    def log_error(self, step: int, error: str, retry: int) -> None:
        self._emit("error", step=step, error=error, retry=retry)

    def log_verification(self, passed: bool, checks: list[str], details: dict[str, Any]) -> None:
        self._emit("verification", passed=passed, checks=checks, details=details)

    def log_run_end(self, result: RunResult) -> None:
        total_ms = int((result.ended_at - result.started_at).total_seconds() * 1000)
        self._emit(
            "run_end",
            status=result.status,
            total_steps=len(result.steps),
            total_ms=total_ms,
            summary=result.summary,
        )

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> Tracer:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
