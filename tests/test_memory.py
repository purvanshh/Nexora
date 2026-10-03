"""Memory scratchpad tests."""

from __future__ import annotations

from agent.memory import Memory
from agent.models import Observation, ToolCall


def test_facts_persist_and_overwrite() -> None:
    mem = Memory(task="t")
    mem.remember("invoice_amount", 10, 0)
    mem.remember("invoice_amount", 20, 1)
    assert mem.facts_dict()["invoice_amount"] == 20
    assert len(mem.facts) == 1


def test_step_ordering() -> None:
    mem = Memory(task="t")
    mem.add_step(0, "a", ToolCall(tool="api", args={}), Observation(ok=True))
    mem.add_step(1, "b", ToolCall(tool="files", args={}), Observation(ok=True))
    assert [s.index for s in mem.steps] == [0, 1]


def test_consecutive_identical_failures() -> None:
    mem = Memory(task="t")
    call = ToolCall(tool="api", args={"path": "/x"})
    mem.add_step(0, "t", call, Observation(ok=False, error="boom"))
    mem.add_step(1, "t", call, Observation(ok=False, error="boom"))
    assert mem.consecutive_identical_failures()
