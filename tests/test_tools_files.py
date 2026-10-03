"""FileTool unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools.files import FileArgs, FileTool


@pytest.mark.asyncio
async def test_write_read_json_roundtrip(workspace: Path) -> None:
    tool = FileTool(workspace)
    w = await tool.run(
        FileArgs(action="write", path="inv.json", content={"amount": 12.5}, format="json")
    )
    assert w.ok
    r = await tool.run(FileArgs(action="read", path="inv.json"))
    assert r.ok
    assert r.data is not None
    assert r.data["content"]["amount"] == 12.5


@pytest.mark.asyncio
async def test_path_traversal_blocked(workspace: Path) -> None:
    tool = FileTool(workspace)
    obs = await tool.run(FileArgs(action="read", path="../secrets.txt"))
    assert not obs.ok
    assert obs.error is not None
    assert "sandbox" in obs.error.lower() or "escapes" in obs.error.lower()


@pytest.mark.asyncio
async def test_malformed_json_handled(workspace: Path) -> None:
    bad = workspace / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    tool = FileTool(workspace)
    obs = await tool.run(FileArgs(action="read", path="bad.json"))
    assert not obs.ok
    assert "Malformed JSON" in (obs.error or "")


@pytest.mark.asyncio
async def test_list_directory(workspace: Path) -> None:
    (workspace / "a.txt").write_text("hi", encoding="utf-8")
    tool = FileTool(workspace)
    obs = await tool.run(FileArgs(action="list", path="."))
    assert obs.ok
    assert obs.data is not None
    assert "a.txt" in obs.data["entries"]
