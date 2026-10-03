"""Prompt builder + LLM chat for the ReAct planner."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Protocol

from openai import AsyncOpenAI

from agent.config import Settings, get_settings
from agent.memory import Memory
from agent.models import LLMResponse, ToolCall


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def build_prompt(
    memory: Memory,
    tools_schema: list[dict[str, Any]],
    system_template: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    template = system_template or load_prompt("system.md")
    facts_block = json.dumps(memory.facts_dict(), indent=2, default=str)
    tools_block = json.dumps(tools_schema, indent=2)
    system = (
        template.replace("{tool_schemas}", tools_block)
        .replace("{facts}", facts_block)
        .replace("{task}", memory.task)
    )

    messages: list[dict[str, str]] = [
        {
            "role": "user",
            "content": (
                f"Task: {memory.task}\n\n"
                "Decide the next action. Use a tool, remember a fact, ask the user, "
                "or finish when done."
            ),
        }
    ]

    for step in memory.steps:
        thought = step.thought or ""
        if step.tool_call:
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        f"Thought: {thought}\n"
                        f"Action: {step.tool_call.tool}\n"
                        f"Args: {json.dumps(step.tool_call.args)}"
                    ),
                }
            )
        if step.observation:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Observation(ok={step.observation.ok}): "
                        f"{json.dumps(step.observation.model_dump(), default=str)}"
                    ),
                }
            )

    return system, messages


class OpenAILLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = AsyncOpenAI(api_key=self.settings.openai_api_key or None)

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        started = time.perf_counter()
        kwargs: dict[str, Any] = {
            "model": self.settings.agent_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0.2,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = response.usage
        message = response.choices[0].message
        thought = message.content or ""

        if message.tool_calls:
            call = message.tool_calls[0]
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "finish":
                return LLMResponse(
                    thought=thought,
                    is_finish=True,
                    summary=str(args.get("summary", thought)),
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    latency_ms=latency_ms,
                )

            return LLMResponse(
                thought=thought,
                is_finish=False,
                tool_call=ToolCall(
                    tool=name,
                    args=args,
                    reasoning=thought,
                ),
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )

        # Fallback: try to parse a finish from free text
        lowered = thought.lower()
        if "finish" in lowered or "task complete" in lowered:
            return LLMResponse(
                thought=thought,
                is_finish=True,
                summary=thought,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
            )

        return LLMResponse(
            thought=thought,
            is_finish=False,
            tool_call=None,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
        )


class StubLLMClient:
    """Deterministic LLM for tests: yields a scripted sequence of responses."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self.script = list(script)
        self.calls = 0

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if self.calls >= len(self.script):
            return LLMResponse(
                thought="No more scripted actions",
                is_finish=True,
                summary="Stub LLM exhausted script",
            )
        resp = self.script[self.calls]
        self.calls += 1
        return resp
