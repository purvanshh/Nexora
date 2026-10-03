"""AskUser menu normalization tests."""

from __future__ import annotations

import pytest

from agent.tools.ask_user import AskUserArgs, AskUserTool, MENU_OPTIONS


def test_normalize_aliases() -> None:
    assert AskUserTool.normalize_answer("r", MENU_OPTIONS) == "retry"
    assert AskUserTool.normalize_answer("ABORT", MENU_OPTIONS) == "abort"
    assert AskUserTool.normalize_answer("i dont know", MENU_OPTIONS) is None


@pytest.mark.asyncio
async def test_unclear_defaults_to_abort_after_two() -> None:
    tool = AskUserTool(callback=lambda q, o: "i dont know")
    first = await tool.run(AskUserArgs(question="stuck?", options=list(MENU_OPTIONS)))
    assert first.ok is False
    second = await tool.run(AskUserArgs(question="stuck?", options=list(MENU_OPTIONS)))
    assert second.ok is True
    assert second.data is not None
    assert second.data["normalized"] == "abort"
