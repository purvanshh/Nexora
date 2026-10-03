# DESIGN — Autonomous AI Task Worker

## Why ReAct

The agent interleaves reasoning with tool use. When a step fails (selector timeout, HTTP 500 from chaos mode, malformed email), the next planner call sees the error in memory and can pivot. That flexibility is essential for reliability in a tool-using agent.

## Why not plan-and-execute

A full upfront plan looks tidy in demos, then collapses when reality diverges — which is most of the time. Re-planning every step costs a few extra LLM calls but avoids brittle multi-step scripts.

## Why a separate verifier

The executor can hallucinate success ("form submitted") while the finance DB stays empty. The verifier never trusts that claim: it independently re-queries `GET /api/invoices` (or payslips) and compares amount/date (or net pay) to scratchpad facts. Failed verification yields `partial`, not an infinite repair loop.

## Why a mock app

The brief forbids real credentials and live third-party sites. A local FastAPI app still exercises real HTTP, real HTML, and real Playwright DOM actions — with deterministic seed data and injectable failures (`CHAOS=1`).

## Why no agent framework

LangChain/CrewAI hide the loop behind abstractions. This prototype's value is showing we understand planning, tool contracts, retries, escalation, and verification — so the ReAct loop is custom and short enough to read in one sitting.

## Failure taxonomy

| Class | Response |
|---|---|
| Transient (timeout, 500) | Retry same tool up to N=2 with backoff (`CHAOS=1` proves this) |
| No progress (≥3 idle steps) | Constrained `ask_user` menu: retry / skip / abort / inform |
| Ambiguity (multiple matches) | `ask_user` |
| Scope violation (extra writes) | Verifier fails with `scope_violation` — run is not success |
| Impossible / exhausted | Report `partial` or `failed` with evidence |

## Scope as a product constraint

An autonomous worker that completes the asked question *and* mutates unrelated systems is a liability. Verification therefore inspects the mutation log from the run trace, not only the final claimed fact.

## Cost / latency budget

- Max ~15 ReAct steps + 1 verifier pass → well under ~30 LLM calls/run
- Wall-clock target: < 3 minutes for the primary demo
- Model default: `gpt-4o-mini` (~<$0.10/run at typical usage)
