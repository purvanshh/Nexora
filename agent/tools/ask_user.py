"""Human-in-the-loop clarification / approval tool."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from agent.models import Observation
from agent.tools.base import Tool

AskCallback = Callable[[str, list[str] | None], Awaitable[str] | str]

MENU_OPTIONS = ["retry", "skip", "abort"]
APPROVAL_OPTIONS = ["approve", "reject"]

# Global aliases used only when they map into the offered options.
_ALIASES = {
    "r": "retry",
    "retry": "retry",
    "s": "skip",
    "skip": "skip",
    "a": "abort",
    "abort": "abort",
    "y": "approve",
    "yes": "approve",
    "approve": "approve",
    "n": "reject",
    "no": "reject",
    "reject": "reject",
}


class AskUserArgs(BaseModel):
    question: str
    options: list[str] | None = Field(
        default=None,
        description="Optional multiple-choice options",
    )


def format_menu(options: list[str]) -> str:
    """Render (a)pprove / (r)eject style shortcuts from option words."""
    parts: list[str] = []
    for opt in options:
        if not opt:
            continue
        parts.append(f"({opt[0]}){opt[1:]}")
    return " / ".join(parts)


class AskUserTool(Tool):
    name = "ask_user"
    description = (
        "Ask the human via a constrained menu. Use for escalation "
        "(retry/skip/abort) or write approval (approve/reject)."
    )
    args_schema = AskUserArgs

    def __init__(self, callback: AskCallback | None = None) -> None:
        self.callback = callback
        self._unclear_count = 0

    @staticmethod
    def normalize_answer(raw: str, options: list[str]) -> str | None:
        text = raw.strip().lower()
        if not text or not options:
            return None
        # Exact match against offered options first.
        for opt in options:
            if text == opt.lower():
                return opt
        # First-letter / "(x)ption" against offered options (so "a" = approve
        # when approve is offered, abort when abort is offered).
        for opt in options:
            initial = opt.lower()[0]
            if text == initial or text.startswith(initial + ")"):
                return opt
        # Global aliases only if they land in the offered set.
        if text in _ALIASES:
            mapped = _ALIASES[text]
            for opt in options:
                if opt.lower() == mapped:
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
                prompt = (
                    f"{args.question}\n"
                    f"Choose one: {format_menu(options)}\n"
                    f"Options: {', '.join(options)}\n> "
                )
                answer = input(prompt)

            raw = str(answer)
            normalized = self.normalize_answer(raw, options)
            if normalized is None:
                self._unclear_count += 1
                if self._unclear_count >= 2:
                    # Prefer reject/abort as the safe default when offered.
                    if "reject" in options:
                        normalized = "reject"
                    elif "abort" in options:
                        normalized = "abort"
                    else:
                        normalized = options[-1]
                    note = "unclear_answer_defaulted_to_safe_stop"
                else:
                    return Observation(
                        ok=False,
                        error=(
                            f"Unclear answer. Reply with one of: {', '.join(options)} "
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
