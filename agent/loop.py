"""ReAct agent loop — plan, act, observe, adapt, verify."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent.config import Settings, get_settings
from agent.health import check_mock_app
from agent.memory import Memory
from agent.models import LLMResponse, Observation, RunResult, ToolCall, VerificationResult
from agent.planner import LLMClient, OpenAILLMClient, build_prompt
from agent.summary import build_summary
from agent.tools.ask_user import MENU_OPTIONS
from agent.tools.registry import ToolRegistry, get_default_registry
from agent.tracer import Tracer
from agent.verifier import Verifier


def is_retryable(obs: Observation) -> bool:
    """Retry only transient failures (5xx / connection). Never retry 4xx validation."""
    if obs.ok:
        return False
    status = None
    if obs.data and isinstance(obs.data.get("status_code"), int):
        status = int(obs.data["status_code"])
    if status is not None:
        return 500 <= status < 600
    err = (obs.error or "").lower()
    # Connection / timeout style errors from httpx (no status_code on Observation).
    transient_markers = (
        "timeout",
        "timed out",
        "connecterror",
        "connection",
        "all connection attempts failed",
        "temporarily unavailable",
    )
    return any(marker in err for marker in transient_markers)


def _with_retry_meta(obs: Observation, *, attempts: int, exhausted: bool) -> Observation:
    data = dict(obs.data or {})
    data["attempts"] = attempts
    data["retries_exhausted"] = exhausted
    return obs.model_copy(update={"data": data})


async def execute_with_retry(
    registry: ToolRegistry,
    tool_call: ToolCall,
    *,
    retries: int = 2,
    tracer: Tracer | None = None,
    step_idx: int = 0,
) -> Observation:
    """Retry identical calls only for transient errors; return 4xx immediately."""
    last: Observation | None = None
    attempts = retries + 1
    for attempt in range(attempts):
        obs = await registry.execute(tool_call.tool, tool_call.args)
        if obs.ok:
            return _with_retry_meta(obs, attempts=attempt + 1, exhausted=False)
        last = obs
        if tracer is not None:
            tracer.log_error(step_idx, obs.error or "unknown", retry=attempt)
        if not is_retryable(obs):
            return _with_retry_meta(obs, attempts=attempt + 1, exhausted=False)
        if attempt < attempts - 1:
            await asyncio.sleep(0.5)
    assert last is not None
    return _with_retry_meta(last, attempts=attempts, exhausted=True)


def should_escalate(memory: Memory) -> bool:
    return memory.consecutive_identical_failures() or memory.consecutive_no_progress >= 3


def _abort_summary(memory: Memory) -> str:
    return (
        "Could not complete the task. After exhausting retries the agent "
        "escalated to the user, who chose abort.\n"
        f"Last error: {memory.last_error}\n"
        f"Facts gathered before giving up: {memory.facts_dict()}"
    )


async def _escalate(
    *,
    registry: ToolRegistry,
    memory: Memory,
    tracer: Tracer,
    step_idx: int,
    reason: str,
) -> str | None:
    """Ask the user via constrained menu. Returns normalized action or None."""
    escalate_call = ToolCall(
        tool="ask_user",
        args={
            "question": (
                f"{reason} Here's what I have: {memory.facts_dict()}. "
                f"Last error: {memory.last_error}."
            ),
            "options": list(MENU_OPTIONS),
        },
        reasoning="escalation",
    )
    esc_obs = await execute_with_retry(
        registry,
        escalate_call,
        retries=0,
        tracer=tracer,
        step_idx=step_idx,
    )
    memory.add_step(step_idx, "Escalating to user", escalate_call, esc_obs)
    tracer.log_observation(step_idx, esc_obs)
    if esc_obs.data:
        tracer.log_user_answer(
            step_idx,
            str(esc_obs.data.get("question", "")),
            str(esc_obs.data.get("answer", "")),
            esc_obs.data.get("normalized"),
        )
        return esc_obs.data.get("normalized")
    return None


async def run(
    task: str,
    *,
    max_steps: int | None = None,
    llm: LLMClient | None = None,
    registry: ToolRegistry | None = None,
    settings: Settings | None = None,
    tracer: Tracer | None = None,
    ask_callback: Any | None = None,
    skip_health_check: bool = False,
) -> RunResult:
    settings = settings or get_settings()
    max_steps = max_steps or settings.agent_max_steps
    llm = llm or OpenAILLMClient(settings)
    registry = registry or get_default_registry(settings, ask_callback=ask_callback)
    owns_tracer = tracer is None
    tracer = tracer or Tracer(run_id=uuid4().hex[:12], trace_dir=settings.trace_dir)

    if not skip_health_check:
        await check_mock_app(settings)

    memory = Memory(task=task)
    started = datetime.now(UTC)
    tracer.log_run_start(task, settings.agent_model)
    final_summary = ""
    aborted = False

    try:
        for step_idx in range(max_steps):
            # Soft finish: required facts present and a verifier pass would succeed.
            if memory.required_facts_present() and step_idx > 0:
                soft = await Verifier(settings).verify(task, memory, summary="soft-check")
                if soft.passed:
                    final_summary = build_summary(task, memory, soft)
                    memory.add_step(
                        step_idx,
                        "Soft finish: verifier would pass on current state",
                        ToolCall(tool="finish", args={"summary": final_summary}),
                        Observation(ok=True, data={"soft_finish": True}),
                    )
                    break

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
                obs = Observation(
                    ok=False,
                    error="Planner returned no tool call; please call a tool or finish.",
                )
                facts_before = len(memory.facts)
                memory.add_step(step_idx, response.thought, None, obs)
                tracer.log_observation(step_idx, obs)
                memory.mark_progress(
                    made_progress=memory.evaluate_progress(
                        facts_before=facts_before,
                        tool_call=None,
                        observation=obs,
                    )
                )
                if should_escalate(memory):
                    action = await _escalate(
                        registry=registry,
                        memory=memory,
                        tracer=tracer,
                        step_idx=step_idx,
                        reason="I'm not making progress.",
                    )
                    if action == "abort":
                        aborted = True
                        final_summary = _abort_summary(memory)
                        break
                    if action == "skip":
                        final_summary = (
                            "User chose skip after escalation. Task not completed.\n"
                            f"Facts gathered: {memory.facts_dict()}"
                        )
                        break
                continue

            tool_call = response.tool_call
            tracer.log_thought(step_idx, response.thought, tool_call)
            facts_before = len(memory.facts)

            if tool_call.tool == "remember":
                key = str(tool_call.args.get("key", ""))
                value = tool_call.args.get("value")
                if key:
                    memory.remember(key, value, step_idx)
                obs = Observation(ok=True, data={"key": key, "value": value})
                memory.add_step(step_idx, response.thought, tool_call, obs)
                tracer.log_observation(step_idx, obs)
                memory.mark_progress(made_progress=True)
                continue

            if tool_call.tool == "finish":
                final_summary = str(tool_call.args.get("summary", response.thought))
                memory.add_step(step_idx, response.thought, tool_call, None)
                break

            if tool_call.tool == "ask_user":
                # Ensure menu options are always present.
                args = dict(tool_call.args)
                args.setdefault("options", list(MENU_OPTIONS))
                tool_call = ToolCall(
                    tool="ask_user",
                    args=args,
                    reasoning=tool_call.reasoning,
                )

            obs = await execute_with_retry(
                registry,
                tool_call,
                retries=settings.agent_retries,
                tracer=tracer,
                step_idx=step_idx,
            )
            memory.add_step(step_idx, response.thought, tool_call, obs)
            tracer.log_observation(step_idx, obs)

            if tool_call.tool == "ask_user" and obs.data:
                tracer.log_user_answer(
                    step_idx,
                    str(obs.data.get("question", "")),
                    str(obs.data.get("answer", "")),
                    obs.data.get("normalized"),
                )
                if obs.data.get("normalized") == "abort":
                    aborted = True
                    final_summary = _abort_summary(memory)
                    break

            made = memory.evaluate_progress(
                facts_before=facts_before,
                tool_call=tool_call,
                observation=obs,
            )
            memory.mark_progress(made_progress=made)

            retries_exhausted = bool(obs.data and obs.data.get("retries_exhausted"))
            if retries_exhausted or should_escalate(memory):
                attempts = (obs.data or {}).get("attempts", "?")
                reason = (
                    f"I could not complete the action after {attempts} attempts "
                    "and cannot safely proceed."
                    if retries_exhausted
                    else "I'm stuck after repeated failures or no progress."
                )
                action = await _escalate(
                    registry=registry,
                    memory=memory,
                    tracer=tracer,
                    step_idx=step_idx,
                    reason=reason,
                )
                if action == "abort":
                    aborted = True
                    final_summary = _abort_summary(memory)
                    break
                if action == "skip":
                    final_summary = (
                        "User chose skip after escalation. Task not completed.\n"
                        f"Facts gathered: {memory.facts_dict()}"
                    )
                    break
                if action == "retry":
                    memory.consecutive_no_progress = 0

        if not final_summary:
            final_summary = (
                "Reached max steps without an explicit finish. "
                f"Facts: {memory.facts_dict()}"
            )

        if aborted:
            # Don't re-query finance after a deliberate abort — that reads like a
            # false "verification failed" when the failure was already intentional.
            verification = VerificationResult(
                passed=False,
                checks=[
                    "skipped: user aborted after escalation",
                    "no independent re-query after abort",
                ],
                details={"reason": "user_aborted", "facts": memory.facts_dict()},
                method="skipped_abort",
            )
        else:
            verifier = Verifier(settings)
            verification = await verifier.verify(task, memory, final_summary)
            final_summary = build_summary(
                task, memory, verification, fallback=final_summary
            )

        tracer.log_verification(
            verification.passed,
            verification.checks,
            verification.details,
        )

        evidence: list[str] = []
        for step in memory.steps:
            if step.observation:
                evidence.extend(step.observation.evidence)
        # Preserve order, drop duplicates for the user-facing report.
        evidence = list(dict.fromkeys(evidence))

        if aborted:
            status = "failed"
        elif verification.passed and memory.steps:
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
            user_aborted=aborted,
        )
        tracer.log_run_end(result)
        return result
    finally:
        if owns_tracer:
            tracer.close()
        await registry.aclose()
