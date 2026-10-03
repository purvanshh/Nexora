# DESIGN — Autonomous AI Task Worker

## Why ReAct

The agent interleaves reasoning with tool use. When a step fails (selector timeout, HTTP 500 from chaos mode, malformed email), the next planner call sees the error in memory and can pivot. That flexibility is essential for reliability.

## Why not plan-and-execute

A full upfront plan looks tidy in demos, then collapses when reality diverges — which is most of the time. Re-planning every step costs a few extra LLM calls but avoids brittle multi-step scripts.

## Why a separate verifier

The executor can hallucinate success ("form submitted") while the finance DB stays empty. Worse, it can answer the user's question *and* perform unrelated writes. The verifier:

1. Re-derives the correct outcome from source APIs (does not start from the agent's claim).
2. Confirms system state.
3. Fails on **scope violations** (e.g. creating an invoice during a payslip lookup).

Failed verification yields `partial` / failed — not an infinite repair loop.

## Why a mock app

The brief forbids real credentials and live third-party sites. A local FastAPI app still exercises real HTTP, real HTML, and real Playwright DOM actions — with deterministic seed data and injectable failures (`CHAOS=1`).

## Why no agent framework

LangChain/CrewAI hide the loop behind abstractions. This prototype's value is showing we understand planning, tool contracts, retries, escalation, and verification — so the ReAct loop is custom and short enough to read in one sitting.

## Why Playwright `launch()`, not CDP

`BrowserTool` calls `async_playwright().start()` → `chromium.launch()`. It never `connect_over_cdp` to the mock app. Probes to `GET /json/version` on port 8000 come from IDE/devtools CDP discovery against whatever is listening locally — not from our tool. Invoice runs are prompted to confirm `/finance/invoices` in the real browser after POST.

## Failure taxonomy

| Class | Response |
|---|---|
| Transient (timeout, 500) | Retry same tool up to N=2 with backoff (`make chaos-demo`) |
| No progress (≥3 idle steps) | Constrained `ask_user`: retry / skip / abort / inform |
| Ambiguity | `ask_user` |
| Scope violation | Verifier fails with `scope_violation` |
| Impossible / exhausted | `partial` or `failed` with evidence |

## Scope as a product constraint

An autonomous worker that completes the asked question *and* mutates unrelated systems is a liability. Verification inspects the mutation log from the run, not only the final claimed fact.

## Summaries

User-facing summaries are **templates** filled from scratchpad facts + verifier result (`agent/summary.py`). No second LLM call — numbers cannot drift from remembered facts.

## Cost / latency budget

- Max ~15 ReAct steps + verifier (+ soft-finish check) → well under ~30 LLM calls/run
- `temperature=0` for more deterministic tool selection
- Wall-clock target: < 3 minutes for the primary demo
- Model default: `gpt-4o-mini` (~<$0.10/run at typical usage)
