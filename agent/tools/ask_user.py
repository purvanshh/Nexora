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
        description=(
            "Menu choices. Omit for retry/skip/abort escalation. "
            "Pass an empty list [] for free-text clarification "
            "(ambiguous sender, missing fields, etc.)."
        ),
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
        "Ask the human. Use a menu for write approval (approve/reject) or "
        "escalation (retry/skip/abort). Pass options=[] for free-text "
        "clarification when the task is ambiguous (e.g. zero or multiple "
        "matching senders)."
    )
    args_schema = AskUserArgs

    def __init__(
        self,
        callback: AskCallback | None = None,
        *,
        auto_approve: bool = False,
    ) -> None:
        self.callback = callback
        self.auto_approve = auto_approve
        self._unclear_count = 0

    @staticmethod
    def normalize_answer(raw: str, options: list[str]) -> str | None:
        text = raw.strip().lower()
        if not text or not options:
            return None
        for opt in options:
            if text == opt.lower():
                return opt
        for opt in options:
            initial = opt.lower()[0]
            if text == initial or text.startswith(initial + ")"):
                return opt
        if text in _ALIASES:
            mapped = _ALIASES[text]
            for opt in options:
                if opt.lower() == mapped:
                    return opt
        return None

    async def run(self, args: BaseModel) -> Observation:
        assert isinstance(args, AskUserArgs)
        started = time.perf_counter()
        # None → escalation menu. [] → free-text clarification. else → that menu.
        free_text = args.options is not None and len(args.options) == 0
        options = list(MENU_OPTIONS) if args.options is None else list(args.options)
        try:
            if (
                self.auto_approve
                and not free_text
                and any(o.lower() == "approve" for o in options)
            ):
                raw = "approve"
                normalized: str | None = "approve"
                note = "auto_approve"
            elif self.callback is not None:
                # Callback sees [] for free-text so tests can distinguish modes.
                cb_options: list[str] | None = [] if free_text else options
                answer = self.callback(args.question, cb_options)
                if hasattr(answer, "__await__"):
                    answer = await answer  # type: ignore[misc]
                raw = str(answer)
                if free_text:
                    normalized = raw.strip() or None
                    note = None
                    if not normalized:
                        return Observation(
                            ok=False,
                            error="Empty clarification answer.",
                            data={
                                "question": args.question,
                                "answer": raw,
                                "options": [],
                                "normalized": None,
                                "mode": "clarify",
                            },
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                else:
                    normalized = self.normalize_answer(raw, options)
                    note = None
            elif free_text:
                raw = input(f"{args.question}\n(Free text clarification)\n> ")
                normalized = str(raw).strip() or None
                note = None
                if not normalized:
                    return Observation(
                        ok=False,
                        error="Empty clarification answer.",
                        data={
                            "question": args.question,
                            "answer": raw,
                            "options": [],
                            "normalized": None,
                            "mode": "clarify",
                        },
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
            else:
                prompt = (
                    f"{args.question}\n"
                    f"Choose one: {format_menu(options)}\n"
                    f"Options: {', '.join(options)}\n> "
                )
                raw = str(input(prompt))
                normalized = self.normalize_answer(raw, options)
                note = None

            if free_text:
                self._unclear_count = 0
                return Observation(
                    ok=True,
                    data={
                        "question": args.question,
                        "answer": raw,
                        "normalized": normalized,
                        "options": [],
                        "mode": "clarify",
                    },
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )

            if normalized is None:
                self._unclear_count += 1
                if self._unclear_count >= 2:
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
