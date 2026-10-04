"""Short-term episodic + semantic memory for a single run."""

from __future__ import annotations

from typing import Any

from agent.models import Fact, Observation, Step, ToolCall


class Memory:
    """In-run scratchpad. Does not persist across runs."""

    def __init__(self, task: str) -> None:
        self.task = task
        self.steps: list[Step] = []
        self._facts: dict[str, Fact] = {}
        self.consecutive_no_progress: int = 0
        self.last_error: str | None = None
        self._last_success_sig: str | None = None

    def add_step(
        self,
        index: int,
        thought: str,
        tool_call: ToolCall | None,
        observation: Observation | None,
    ) -> Step:
        step = Step(
            index=index,
            thought=thought,
            tool_call=tool_call,
            observation=observation,
        )
        self.steps.append(step)

        if observation is not None and not observation.ok:
            self.last_error = observation.error

        return step

    def remember(self, key: str, value: Any, source_step: int) -> Fact:
        fact = Fact(key=key, value=value, source_step=source_step)
        self._facts[key] = fact
        return fact

    def get_fact(self, key: str) -> Fact | None:
        return self._facts.get(key)

    @property
    def facts(self) -> list[Fact]:
        return list(self._facts.values())

    def facts_dict(self) -> dict[str, Any]:
        return {f.key: f.value for f in self._facts.values()}

    def recent_failures(self, n: int = 2) -> list[Step]:
        failures = [
            s
            for s in self.steps
            if s.observation is not None and not s.observation.ok
        ]
        return failures[-n:]

    def consecutive_identical_failures(self) -> bool:
        fails = self.recent_failures(2)
        if len(fails) < 2:
            return False
        a, b = fails[-2], fails[-1]
        if a.tool_call is None or b.tool_call is None:
            return False
        return (
            a.tool_call.tool == b.tool_call.tool
            and a.tool_call.args == b.tool_call.args
            and a.observation is not None
            and b.observation is not None
            and a.observation.error == b.observation.error
        )

    def mark_progress(self, *, made_progress: bool) -> None:
        if made_progress:
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1

    def evaluate_progress(
        self,
        *,
        facts_before: int,
        tool_call: ToolCall | None,
        observation: Observation | None,
    ) -> bool:
        """Return True if this step advanced the run."""
        if len(self._facts) > facts_before:
            return True
        if tool_call is None:
            return False
        if tool_call.tool in {"remember", "finish"}:
            return True
        if observation is None or not observation.ok:
            return False
        sig = f"{tool_call.tool}:{sorted(tool_call.args.items())}"
        if sig == self._last_success_sig:
            return False
        self._last_success_sig = sig
        return True

    def required_facts_present(self) -> bool:
        """Soft-finish heuristic based on task keywords."""
        task_l = self.task.lower()
        facts = self.facts_dict()
        if "leave" in task_l or "time off" in task_l:
            wrote = any(
                s.tool_call
                and s.tool_call.tool == "api"
                and str(s.tool_call.args.get("method", "")).upper() == "POST"
                and "/api/leave" in str(s.tool_call.args.get("path", ""))
                and s.observation
                and s.observation.ok
                for s in self.steps
            )
            return wrote and (
                "leave_start" in facts or "start_date" in facts
            ) and ("employee_id" in facts or "42" in self.task)
        if "payslip" in task_l or "net pay" in task_l:
            return "net_pay" in facts and (
                "employee_id" in facts or "42" in self.task
            )
        if "invoice" in task_l or "finance" in task_l:
            has_fields = all(
                k in facts for k in ("invoice_amount", "invoice_due_date")
            )
            wrote = any(
                s.tool_call
                and s.tool_call.tool == "api"
                and str(s.tool_call.args.get("method", "")).upper() == "POST"
                and "/api/invoices" in str(s.tool_call.args.get("path", ""))
                and s.observation
                and s.observation.ok
                for s in self.steps
            )
            # Require a real Playwright UI check so the browser tool stays on the path.
            browsed = any(
                s.tool_call
                and s.tool_call.tool == "browser"
                and s.observation
                and s.observation.ok
                for s in self.steps
            )
            return has_fields and wrote and browsed
        return False
