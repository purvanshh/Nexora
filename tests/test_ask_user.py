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


@pytest.mark.asyncio
async def test_free_text_clarification_mode() -> None:
    tool = AskUserTool(callback=lambda q, o: "use Acme Corp, not Acme Corporation")
    obs = await tool.run(AskUserArgs(question="Which sender?", options=[]))
    assert obs.ok is True
    assert obs.data is not None
    assert obs.data["mode"] == "clarify"
    assert "Acme Corp" in obs.data["normalized"]


@pytest.mark.asyncio
async def test_auto_approve_answers_write_gate() -> None:
    tool = AskUserTool(auto_approve=True)
    obs = await tool.run(
        AskUserArgs(question="Write?", options=list(APPROVAL_OPTIONS))
    )
    assert obs.ok is True
    assert obs.data is not None
    assert obs.data["normalized"] == "approve"
    assert obs.data.get("note") == "auto_approve"
