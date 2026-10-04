# DESIGN: Autonomous AI Task Worker

## Why ReAct

The agent interleaves reasoning with tool use. When a step fails (selector timeout, HTTP 500 from chaos mode, malformed email), the next planner call sees the error in memory and can pivot. That flexibility is essential for reliability.

## Why not plan-and-execute

A full upfront plan looks tidy in demos, then collapses when reality diverges, which is most of the time. Re-planning every step costs a few extra LLM calls but avoids brittle multi-step scripts.

## Why a separate verifier

The executor can hallucinate success ("form submitted") while the finance DB stays empty. Worse, it can answer the user's question and perform unrelated writes. The verifier:

1. Re-derives the correct outcome from source APIs (does not start from the agent's claim).
2. Confirms system state with a separate query.
3. Fails on scope violations (e.g. creating an invoice during a payslip lookup).
4. For leave writes, requires exactly one matching record so a duplicate retry cannot silently pass.

It is independent of the executor's narrative, not of the mock app. After a deliberate user abort/reject, verification is skipped.

Failed verification yields `partial` / failed, not an infinite repair loop.

## Why a pre-write approval gate

Post-failure escalation alone is not enough for a finance write. With `REQUIRE_WRITE_APPROVAL=1` (default), every mutating API call pauses with the exact method, path, and JSON payload and asks approve/reject. Identical approved payloads are not re-prompted across retries.

`AUTO_APPROVE=1` answers approve automatically so reviewers can skim `make demo` without a TTY. Escalation abort and free-text clarification still need a human when they fire.

## Why free-text clarification

Approve/reject and retry/skip/abort cannot answer "which sender?" when zero or multiple records match. `ask_user` with `options=[]` collects free text. The system prompt tells the planner to clarify instead of guessing.

## Why a mock app

The brief forbids real credentials and live third-party sites. A local FastAPI app still exercises real HTTP, real HTML, and real Playwright DOM actions, with deterministic seed data and injectable failures:

- `CHAOS=1`: first invoice POST returns 500, then succeeds (retry demo)
- `PERMANENT_FAIL=1`: every invoice POST returns 500 (escalation demo)

Seed mail includes older Acme invoices, a malformed Acme reminder, and an Acme Corporation decoy sender so "latest Acme Corp" requires correct sender matching.

## Why no agent framework

LangChain / CrewAI / LangGraph hide the loop behind abstractions. This prototype's value is showing we understand planning, tool contracts, retries, approval, clarification, escalation, and verification, so the ReAct loop is custom and short enough to read in one sitting. The ideas overlap with graph-based agents; the implementation stays explicit.

## Why Playwright launch(), not CDP / "computer use"

`BrowserTool` calls `chromium.launch()`. It never `connect_over_cdp` to the mock app. The primary data path is the REST API; the browser is a confirmation step for `/finance/invoices` after a successful invoice POST, not the driver of the whole task.

## Failure taxonomy

| Class | Response |
|---|---|
| Pre-write | Approve/reject menu with exact payload |
| Ambiguity | Free-text `ask_user` (`options=[]`) |
| Transient (timeout, 5xx) | Retry same tool up to N=`AGENT_RETRIES`; invoice may idempotent-recover |
| Semantic (4xx validation) | No retry: return observation; planner must correct args |
| Conflict (409) with matching invoice | Treat as success (idempotent recover) |
| Retries exhausted | Escalate via `ask_user` retry/skip/abort |
| No progress (≥3 idle steps) | Same escalation menu |
| Scope violation | Verifier fails with `scope_violation` |
| Leave duplicates | Verifier fails unless exactly one match |
| User abort / reject | `failed`, facts preserved, verification skipped |

### Honest gaps

- Retry policy and escalation policy are still coupled for permanent 500s: we retry like a blip, then escalate. Production should classify transient vs persistent before retrying.
- Invoice writes have client `invoice_id` + 409 recovery. Leave IDs are server-minted, so a committed-but-500 leave can duplicate on retry. Fix with API-level idempotency keys. The leave verifier at least fails closed on duplicates.
- Deep verification is still per task-kind (`invoice` / `payslip` / `leave`). Adding a new write task means extending the verifier (documented in the README).

## Scope as a product constraint

An autonomous worker that completes the asked question and mutates unrelated systems is a liability. Verification inspects the mutation log from the run, not only the final claimed fact.

## Invoice identity and POST safety

The finance API honors a client-supplied `invoice_id` (409 on conflict). Retries after ambiguous 500s check GET-by-id and treat a matching record as success so we do not create duplicates or die on our own write.

## Summaries

User-facing summaries are templates filled from scratchpad facts + verifier details. They embed compact JSON snapshots of source/target records so evidence is not only a dead `localhost` URL.

## Cost / latency budget

- Max ~15 ReAct steps + verifier (+ soft-finish check): well under ~30 LLM calls/run
- `temperature=0` for more deterministic tool selection
- Model default: `gpt-4o-mini`
- Do not treat interactive wall-clock (including time spent typing at approve prompts) as agent latency
