"""Human-in-the-loop clarification / approval tool."""

from __future__ import annotations

import time
from collections.abc import Callable, Awaitable
from typing import Any

from pydantic import BaseModel, Field

from agent.models import Observation
from agent.tools.base import Tool

AskCallback = Callable[[str, list[str] | None], Awaitable[str] | str]


class AskUserArgs(BaseModel):
    question: str
    options: list[str] | None = Field(
        default=None,
        description="Optional multiple-choice options",
    )


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Ask the human for clarification, choice among options, or approval "
        "before an irreversible action."
    )
    args_schema = AskUserArgs

    def __init__(self, callback: AskCallback | None = None) -> None:
        self.callback = callback

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, AskUserArgs)
        started = time.perf_counter()
        try:
            if self.callback is not None:
                answer = self.callback(args.question, args.options)
                if hasattr(answer, "__await__"):
                    answer = await answer  # type: ignore[misc]
            else:
                prompt = args.question
                if args.options:
                    prompt += "\nOptions: " + ", ".join(args.options)
                prompt += "\n> "
                answer = input(prompt)

            return Observation(
                ok=True,
                data={"question": args.question, "answer": str(answer), "options": args.options},
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return Observation(
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
