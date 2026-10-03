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
