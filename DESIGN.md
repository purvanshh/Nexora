# DESIGN — Autonomous AI Task Worker

## Why ReAct

The agent interleaves reasoning with tool use. When a step fails (selector timeout, HTTP 500 from chaos mode, malformed email), the next planner call sees the error in memory and can pivot. That flexibility is essential for reliability.

## Why not plan-and-execute

A full upfront plan looks tidy in demos, then collapses when reality diverges — which is most of the time. Re-planning every step costs a few extra LLM calls but avoids brittle multi-step scripts.

## Why a separate verifier

The executor can hallucinate success ("form submitted") while the finance DB stays empty. Worse, it can answer the user's question *and* perform unrelated writes. The verifier:

1. Re-derives the correct outcome from source APIs (does not start from the agent's claim).
2. Confirms system state with a separate query (e.g. finance record by invoice ID).
3. Fails on **scope violations** (e.g. creating an invoice during a payslip lookup).

After a deliberate user **abort**, verification is skipped — re-querying finance would look like a second failure on an intentional stop.

Failed verification yields `partial` / failed — not an infinite repair loop.

## Why a mock app

The brief forbids real credentials and live third-party sites. A local FastAPI app still exercises real HTTP, real HTML, and real Playwright DOM actions — with deterministic seed data and injectable failures:

- `CHAOS=1` — first invoice POST returns 500, then succeeds (retry demo)
- `PERMANENT_FAIL=1` — every invoice POST returns 500 (escalation demo)

## Why no agent framework

LangChain/CrewAI hide the loop behind abstractions. This prototype's value is showing we understand planning, tool contracts, retries, escalation, and verification — so the ReAct loop is custom and short enough to read in one sitting.

## Why Playwright `launch()`, not CDP

`BrowserTool` calls `async_playwright().start()` → `chromium.launch()`. It never `connect_over_cdp` to the mock app. Probes to `GET /json/version` on port 8000 come from IDE/devtools CDP discovery against whatever is listening locally — not from our tool. Invoice runs are prompted to confirm `/finance/invoices` in the real browser after POST.

## Failure taxonomy

| Class | Response |
|---|---|
| Transient (timeout, 5xx) | Retry same tool up to N=`AGENT_RETRIES` with backoff (`make chaos-demo`) |
| Semantic (4xx validation / conflict) | **No retry** — return observation; planner must correct args |
| Retries exhausted (incl. permanent 500) | Escalate via `ask_user` (`make escalate-demo`) |
| No progress (≥3 idle steps) | Same constrained menu |
| Ambiguity | `ask_user` |
| Scope violation | Verifier fails with `scope_violation` |
| User abort | `failed`, facts preserved, verification skipped, clean exit |

### Escalation menu

Options are exactly `["retry", "skip", "abort"]` (shortcuts `r` / `s` / `a`). Free-text "inform" was removed: the prototype cannot honor an open-ended info branch, and offering it created a dead loop.

Escalation copy states that the agent could not complete the action after N attempts — it does **not** claim the failure was transient, because `PERMANENT_FAIL` is persistent.

### Honest gap

Retry policy and escalation policy are still coupled: a permanently-500ing endpoint is treated like a blip (retry N times) before the human is asked. A production worker should classify transient vs persistent *before* retrying, and escalate immediately on the latter.

## Scope as a product constraint

An autonomous worker that completes the asked question *and* mutates unrelated systems is a liability. Verification inspects the mutation log from the run, not only the final claimed fact.

## Invoice identity

The finance API honors a client-supplied `invoice_id` when present (409 on conflict). The verifier re-fetches the source email and checks that the saved record's ID matches — so the summary cannot invent a different invoice number than the mail.

## Summaries

User-facing summaries are **templates** filled from scratchpad facts + verifier result (`agent/summary.py`). No second LLM call — numbers cannot drift from remembered facts. On abort, the summary honestly reports that the task could not be completed and lists facts gathered before giving up.

## Cost / latency budget

- Max ~15 ReAct steps + verifier (+ soft-finish check) → well under ~30 LLM calls/run
- `temperature=0` for more deterministic tool selection
- Wall-clock target: < 3 minutes for the primary demo
- Model default: `gpt-4o-mini` (~<$0.10/run at typical usage)
