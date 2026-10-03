"""BrowserTool tests against the live mock app UI."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.tools.browser import BrowserArgs, BrowserTool


@pytest.mark.asyncio
async def test_browser_goto_and_extract(mock_app: str, tmp_path: Path) -> None:
    tool = BrowserTool(base_url=mock_app, headless=True, evidence_dir=tmp_path / "shots")
    try:
        obs = await tool.run(BrowserArgs(action="goto", url="/mail"))
        assert obs.ok, obs.error
        assert obs.data is not None
        assert "Inbox" in (obs.data.get("title") or "") or "Inbox" in obs.data.get(
            "text_snippet", ""
        )
        assert obs.evidence, "expected auto-screenshot"

        extract = await tool.run(
            BrowserArgs(action="extract", selector="[data-testid='inbox-title']")
        )
        assert extract.ok, extract.error
        assert extract.data is not None
        assert "Inbox" in extract.data["text"]
    finally:
        await tool.close()


@pytest.mark.asyncio
async def test_browser_screenshot(mock_app: str, tmp_path: Path) -> None:
    out = tmp_path / "manual.png"
    tool = BrowserTool(base_url=mock_app, headless=True, evidence_dir=tmp_path / "shots")
    try:
        await tool.run(BrowserArgs(action="goto", url="/finance"))
        obs = await tool.run(BrowserArgs(action="screenshot", path=str(out)))
        assert obs.ok, obs.error
        assert out.exists()
    finally:
        await tool.close()
