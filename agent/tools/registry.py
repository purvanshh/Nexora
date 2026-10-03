"""Tool discovery, schema export, and dispatch."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from agent.config import Settings, get_settings
from agent.models import Observation
from agent.tools.api import APITool
from agent.tools.ask_user import AskCallback, AskUserTool
from agent.tools.base import Tool
from agent.tools.browser import BrowserTool
from agent.tools.files import FileTool


class RememberArgs(BaseModel):
    key: str
    value: Any


class FinishArgs(BaseModel):
    summary: str


class _MetaTool(Tool):
    """Lightweight wrapper so remember/finish appear in OpenAI tool schemas."""

    def __init__(self, name: str, description: str, args_schema: type[BaseModel]) -> None:
        self.name = name
        self.description = description
        self.args_schema = args_schema

    async def run(self, args: BaseModel) -> Observation:
        return Observation(ok=True, data=args.model_dump())


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.browser: BrowserTool | None = None

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        if isinstance(tool, BrowserTool):
            self.browser = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, args: dict[str, Any]) -> Observation:
        tool = self._tools.get(name)
        if tool is None:
            return Observation(ok=False, error=f"Unknown tool: {name}", duration_ms=0)
        started = time.perf_counter()
        try:
            parsed = tool.args_schema.model_validate(args)
        except ValidationError as exc:
            return Observation(
                ok=False,
                error=f"Invalid args for {name}: {exc}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        return await tool.run(parsed)

    async def aclose(self) -> None:
        if self.browser is not None:
            await self.browser.close()


def get_default_registry(
    settings: Settings | None = None,
    *,
    ask_callback: AskCallback | None = None,
    evidence_dir: Path | None = None,
) -> ToolRegistry:
    settings = settings or get_settings()
    registry = ToolRegistry()
    registry.register(FileTool(settings.workspace_dir))
    registry.register(APITool(settings.mock_app_url))
    registry.register(
        BrowserTool(
            base_url=settings.mock_app_url,
            headless=settings.headless,
            evidence_dir=evidence_dir or (settings.trace_dir / "browser"),
        )
    )
    registry.register(AskUserTool(callback=ask_callback))
    registry.register(
        _MetaTool(
            "remember",
            "Store a discovered fact in scratchpad memory for later steps.",
            RememberArgs,
        )
    )
    registry.register(
        _MetaTool(
            "finish",
            "Mark the task complete and provide a concise summary.",
            FinishArgs,
        )
    )
    return registry
