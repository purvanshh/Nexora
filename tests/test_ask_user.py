"""AskUser menu normalization tests."""

from __future__ import annotations

import pytest

from agent.tools.ask_user import (
    APPROVAL_OPTIONS,
    AskUserArgs,
    AskUserTool,
    MENU_OPTIONS,
    format_menu,
)


def test_normalize_aliases() -> None:
    assert AskUserTool.normalize_answer("r", MENU_OPTIONS) == "retry"
    assert AskUserTool.normalize_answer("ABORT", MENU_OPTIONS) == "abort"
    assert AskUserTool.normalize_answer("i dont know", MENU_OPTIONS) is None


def test_normalize_approval_menu() -> None:
    # First letter binds to offered options, so "a" means approve here, not abort.
    assert AskUserTool.normalize_answer("a", APPROVAL_OPTIONS) == "approve"
    assert AskUserTool.normalize_answer("y", APPROVAL_OPTIONS) == "approve"
    assert AskUserTool.normalize_answer("r", APPROVAL_OPTIONS) == "reject"
    assert AskUserTool.normalize_answer("n", APPROVAL_OPTIONS) == "reject"


def test_format_menu() -> None:
    assert "(a)pprove" in format_menu(APPROVAL_OPTIONS)
    assert "(r)etry" in format_menu(MENU_OPTIONS)


@pytest.mark.asyncio
async def test_unclear_defaults_to_abort_after_two() -> None:
    tool = AskUserTool(callback=lambda q, o: "i dont know")
    first = await tool.run(AskUserArgs(question="stuck?", options=list(MENU_OPTIONS)))
    assert first.ok is False
    second = await tool.run(AskUserArgs(question="stuck?", options=list(MENU_OPTIONS)))
    assert second.ok is True
    assert second.data is not None
    assert second.data["normalized"] == "abort"


@pytest.mark.asyncio
async def test_unclear_defaults_to_reject_on_approval_menu() -> None:
    tool = AskUserTool(callback=lambda q, o: "???")
    first = await tool.run(
        AskUserArgs(question="write?", options=list(APPROVAL_OPTIONS))
    )
    assert first.ok is False
    second = await tool.run(
        AskUserArgs(question="write?", options=list(APPROVAL_OPTIONS))
    )
    assert second.ok is True
    assert second.data is not None
    assert second.data["normalized"] == "reject"
