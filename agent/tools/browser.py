"""Playwright browser tool against the local mock web UI."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.models import Observation
from agent.tools.base import Tool


class BrowserArgs(BaseModel):
    action: Literal["goto", "click", "fill", "extract", "screenshot", "wait_for"]
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    path: str | None = Field(default=None, description="Screenshot output path")
    timeout_ms: int = 10_000


class BrowserTool(Tool):
    name = "browser"
    description = (
        "Drive the mock company web UI with Playwright. Actions: goto, click, fill, "
        "extract, screenshot, wait_for. Prefer role=/text=/data-testid= selectors."
    )
    args_schema = BrowserArgs

    def __init__(
        self,
        *,
        base_url: str,
        headless: bool = True,
        evidence_dir: Path | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.evidence_dir = Path(evidence_dir or "./traces/browser")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None
        self._step = 0

    async def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        from playwright.async_api import async_playwright

        # Always launch a dedicated Chromium — never connect_over_cdp to the mock app.
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-dev-shm-usage"],
        )
        self._page = await self._browser.new_page()
        return self._page

    async def close(self) -> None:
        # Visible demos: keep Chromium up so the UI can be shown on camera.
        # Set BROWSER_HOLD_SECONDS=0 to skip (default is interactive Enter).
        if not self.headless and self._browser is not None:
            hold_env = os.environ.get("BROWSER_HOLD_SECONDS", "").strip()
            if hold_env == "0":
                pass
            elif hold_env.isdigit() and int(hold_env) > 0:
                print(
                    f"\n[browser] Holding Chromium open for {hold_env}s…",
                    flush=True,
                )
                await asyncio.sleep(int(hold_env))
            else:
                print(
                    "\n[browser] Holding Chromium open for the demo. "
                    "Look at /finance/invoices, then press Enter to close…",
                    flush=True,
                )
                await asyncio.to_thread(input)

        browser, playwright = self._browser, self._playwright
        self._page = None
        self._browser = None
        self._playwright = None
        if browser is not None:
            await browser.close()
        if playwright is not None:
            await playwright.stop()

    def _abs_url(self, url: str) -> str:
        if url.startswith("http"):
            return url
        return f"{self.base_url}{url}"

    async def _auto_screenshot(self) -> str | None:
        if self._page is None:
            return None
        self._step += 1
        path = self.evidence_dir / f"step_{self._step}.png"
        await self._page.screenshot(path=str(path), full_page=True)
        return str(path)

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, BrowserArgs)
        started = time.perf_counter()
        evidence: list[str] = []
        try:
            page = await self._ensure_page()
            data: dict[str, Any] = {"action": args.action}

            if args.action == "goto":
                if not args.url:
                    return Observation(ok=False, error="url required for goto", duration_ms=_ms(started))
                resp = await page.goto(self._abs_url(args.url), timeout=args.timeout_ms)
                title = await page.title()
                text = await page.inner_text("body")
                data.update(
                    {
                        "title": title,
                        "status": resp.status if resp else None,
                        "text_snippet": text[:800],
                    }
                )
            elif args.action == "click":
                if not args.selector:
                    return Observation(
                        ok=False, error="selector required for click", duration_ms=_ms(started)
                    )
                await page.click(args.selector, timeout=args.timeout_ms)
                data["clicked"] = args.selector
            elif args.action == "fill":
                if not args.selector or args.value is None:
                    return Observation(
                        ok=False,
                        error="selector and value required for fill",
                        duration_ms=_ms(started),
                    )
                await page.fill(args.selector, args.value, timeout=args.timeout_ms)
                data["filled"] = args.selector
            elif args.action == "extract":
                if not args.selector:
                    return Observation(
                        ok=False, error="selector required for extract", duration_ms=_ms(started)
                    )
                text = await page.inner_text(args.selector, timeout=args.timeout_ms)
                data["text"] = text
            elif args.action == "wait_for":
                if not args.selector:
                    return Observation(
                        ok=False, error="selector required for wait_for", duration_ms=_ms(started)
                    )
                await page.wait_for_selector(args.selector, timeout=args.timeout_ms)
                data["waited_for"] = args.selector
            elif args.action == "screenshot":
                out = Path(args.path) if args.path else self.evidence_dir / "manual.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(out), full_page=True)
                evidence.append(str(out))
                data["path"] = str(out)

            shot = await self._auto_screenshot()
            if shot:
                evidence.append(shot)

            return Observation(
                ok=True,
                data=data,
                duration_ms=_ms(started),
                evidence=evidence,
            )
        except Exception as exc:  # noqa: BLE001
            try:
                shot = await self._auto_screenshot()
                if shot:
                    evidence.append(shot)
            except Exception:
                pass
            return Observation(
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=_ms(started),
                evidence=evidence,
            )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
