"""Human-in-the-loop clarification / approval tool."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from agent.models import Observation
from agent.tools.base import Tool

AskCallback = Callable[[str, list[str] | None], Awaitable[str] | str]

MENU_OPTIONS = ["retry", "skip", "abort"]
_ALIASES = {
    "r": "retry",
    "retry": "retry",
    "s": "skip",
    "skip": "skip",
    "a": "abort",
    "abort": "abort",
}


class AskUserArgs(BaseModel):
    question: str
    options: list[str] | None = Field(
        default=None,
        description="Optional multiple-choice options",
    )


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Ask the human for clarification via a constrained menu: "
        "retry / skip / abort. Use when stuck or before irreversible actions."
    )
    args_schema = AskUserArgs

    def __init__(self, callback: AskCallback | None = None) -> None:
        self.callback = callback
        self._unclear_count = 0

    @staticmethod
    def normalize_answer(raw: str, options: list[str]) -> str | None:
        text = raw.strip().lower()
        if text in _ALIASES:
            mapped = _ALIASES[text]
            return mapped if mapped in options or mapped in MENU_OPTIONS else None
        for opt in options:
            if text == opt.lower() or text.startswith(opt.lower()[0] + ")"):
                return opt
        return None

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, AskUserArgs)
        started = time.perf_counter()
        options = args.options or list(MENU_OPTIONS)
        try:
            if self.callback is not None:
                answer = self.callback(args.question, options)
                if hasattr(answer, "__await__"):
                    answer = await answer  # type: ignore[misc]
            else:
                prompt = args.question
                prompt += (
                    "\nChoose one: (r)etry / (s)kip / (a)bort"
                    f"\nOptions: {', '.join(options)}\n> "
                )
                answer = input(prompt)

            raw = str(answer)
            normalized = self.normalize_answer(raw, options)
            if normalized is None:
                self._unclear_count += 1
                if self._unclear_count >= 2:
                    normalized = "abort"
                    note = "unclear_answer_defaulted_to_abort"
                else:
                    return Observation(
                        ok=False,
                        error=(
                            "Unclear answer. Reply with retry, skip, or abort "
                            f"(attempt {self._unclear_count}/2)."
                        ),
                        data={
                            "question": args.question,
                            "answer": raw,
                            "options": options,
                            "normalized": None,
                        },
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
            else:
                self._unclear_count = 0
                note = None

            data = {
                "question": args.question,
                "answer": raw,
                "normalized": normalized,
                "options": options,
            }
            if note:
                data["note"] = note
            return Observation(
                ok=True,
                data=data,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            return Observation(
                ok=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
