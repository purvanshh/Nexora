"""ReAct agent loop — plan, act, observe, adapt, verify."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent.config import Settings, get_settings
from agent.errors import EscalationNeeded
from agent.memory import Memory
from agent.models import LLMResponse, Observation, RunResult, ToolCall
from agent.planner import LLMClient, OpenAILLMClient, build_prompt
from agent.tools.registry import ToolRegistry, get_default_registry
from agent.tracer import Tracer
from agent.verifier import Verifier


async def execute_with_retry(
    registry: ToolRegistry,
    tool_call: ToolCall,
    *,
    retries: int = 2,
    tracer: Tracer | None = None,
    step_idx: int = 0,
) -> Observation:
    """Run a tool with up to `retries` identical retries on failure."""
    last: Observation | None = None
    attempts = retries + 1
    for attempt in range(attempts):
        obs = await registry.execute(tool_call.tool, tool_call.args)
        if obs.ok:
            return obs
        last = obs
        if tracer is not None:
            tracer.log_error(step_idx, obs.error or "unknown", retry=attempt)
        if attempt < attempts - 1:
            await asyncio.sleep(0.5)
    assert last is not None
    return last


def should_escalate(memory: Memory) -> bool:
    return memory.consecutive_identical_failures()


async def run(
    task: str,
    *,
    max_steps: int | None = None,
    llm: LLMClient | None = None,
    registry: ToolRegistry | None = None,
    settings: Settings | None = None,
    tracer: Tracer | None = None,
    ask_callback: Any | None = None,
) -> RunResult:
    settings = settings or get_settings()
    max_steps = max_steps or settings.agent_max_steps
    llm = llm or OpenAILLMClient(settings)
    registry = registry or get_default_registry(settings, ask_callback=ask_callback)
    owns_tracer = tracer is None
    tracer = tracer or Tracer(run_id=uuid4().hex[:12], trace_dir=settings.trace_dir)

    memory = Memory(task=task)
    started = datetime.now(UTC)
    tracer.log_run_start(task, settings.agent_model)
    final_summary = ""

    try:
        for step_idx in range(max_steps):
            tools_schema = registry.openai_schemas()
            system, messages = build_prompt(memory, tools_schema)
            response: LLMResponse = await llm.chat(
                system=system,
                messages=messages,
                tools=tools_schema,
            )
            tracer.log_llm_call(
                step_idx,
                response.prompt_tokens,
                response.completion_tokens,
                response.latency_ms,
            )

            if response.is_finish:
                final_summary = response.summary or response.thought
                memory.add_step(step_idx, response.thought, None, None)
                break

            if response.tool_call is None:
                # Model returned prose without a tool — nudge via memory as a failed step
                obs = Observation(
                    ok=False,
                    error="Planner returned no tool call; please call a tool or finish.",
                )
                memory.add_step(step_idx, response.thought, None, obs)
                tracer.log_observation(step_idx, obs)
                continue

            tool_call = response.tool_call
            tracer.log_thought(step_idx, response.thought, tool_call)

            # Internal remember action
            if tool_call.tool == "remember":
                key = str(tool_call.args.get("key", ""))
                value = tool_call.args.get("value")
                if key:
                    memory.remember(key, value, step_idx)
                obs = Observation(ok=True, data={"key": key, "value": value})
                memory.add_step(step_idx, response.thought, tool_call, obs)
                tracer.log_observation(step_idx, obs)
                continue

            if tool_call.tool == "finish":
                final_summary = str(tool_call.args.get("summary", response.thought))
                memory.add_step(step_idx, response.thought, tool_call, None)
                break

            obs = await execute_with_retry(
                registry,
                tool_call,
                retries=settings.agent_retries,
                tracer=tracer,
                step_idx=step_idx,
            )
            memory.add_step(step_idx, response.thought, tool_call, obs)
            tracer.log_observation(step_idx, obs)

            if should_escalate(memory):
                try:
                    escalate_call = ToolCall(
                        tool="ask_user",
                        args={
                            "question": (
                                "I'm stuck after repeated identical failures. "
                                f"Last error: {obs.error}. How should I proceed?"
                            )
                        },
                        reasoning="escalation after identical failures",
                    )
                    esc_obs = await execute_with_retry(
                        registry,
                        escalate_call,
                        retries=0,
                        tracer=tracer,
                        step_idx=step_idx,
                    )
                    memory.add_step(
                        step_idx,
                        "Escalating to user after repeated failures",
                        escalate_call,
                        esc_obs,
                    )
                    tracer.log_observation(step_idx, esc_obs)
                except EscalationNeeded as exc:
                    memory.add_step(
                        step_idx,
                        f"Escalation needed: {exc.question}",
                        None,
                        Observation(ok=False, error=str(exc)),
                    )

        if not final_summary:
            final_summary = (
                "Reached max steps without an explicit finish. "
                f"Facts: {memory.facts_dict()}"
            )

        verifier = Verifier(settings)
        verification = await verifier.verify(task, memory, final_summary)
        tracer.log_verification(
            verification.passed,
            verification.checks,
            verification.details,
        )

        evidence: list[str] = []
        for step in memory.steps:
            if step.observation:
                evidence.extend(step.observation.evidence)

        if verification.passed and memory.steps:
            status = "success"
        elif memory.steps:
            status = "partial"
        else:
            status = "failed"

        ended = datetime.now(UTC)
        result = RunResult(
            task=task,
            status=status,
            steps=memory.steps,
            facts=memory.facts,
            verification=verification,
            summary=final_summary,
            evidence_paths=evidence,
            started_at=started,
            ended_at=ended,
        )
        tracer.log_run_end(result)
        return result
    finally:
        if owns_tracer:
            tracer.close()
