# Nexora — Autonomous AI Task Worker

A narrow intern prototype: give it a natural-language office task, and it **plans, executes real tools** against a local mock company (mail + finance + HR), **retries transient failures**, **escalates to a human** when it cannot safely proceed, **independently verifies** the outcome (including scope), and returns a concise business summary with evidence.

> A narrow prototype that genuinely works beats a broad system where most functionality is mocked.

## Demo video

**[Watch the walkthrough](https://drive.google.com/drive/folders/1yz5ZYBMtdx6RqCuQBd87ZDCGW2o-jGrZ?usp=sharing)** — ~5 min: primary demo → trace → chaos retry → escalation/abort → secondary → limitations.

## Setup (5 commands)

```bash
git clone https://github.com/purvanshh/Nexora.git && cd Nexora
cp .env.example .env          # set OPENAI_API_KEY
make install                  # deps + Playwright Chromium
make demo                     # boots mock app + primary scenario
make test                     # tools + verifier + stubbed E2E
```

## Demo scenarios

Same agent loop; only the task prompt and failure injection differ:

| Target | What it proves |
|---|---|
| `make demo` | Happy path: mail → extract → POST invoice → confirm |
| `make chaos-demo` | `CHAOS=1`: first invoice POST returns **500**, retry → **201** |
| `make escalate-demo` | `PERMANENT_FAIL=1`: every POST **500** → retries exhaust → menu → type **`a`** to abort |
| `make secondary` | Payslip lookup; same loop, **no** finance writes |

Visible browser (Playwright launches its own Chromium — not CDP against the mock app):

```bash
HEADLESS=false make demo
```

On escalate-demo, when prompted choose one of `(r)etry / (s)kip / (a)bort`. For the recorded abort path, type **`a`**.

## Architecture

```
┌──────────────┐
│  CLI / UI    │  ← natural language task in
└──────┬───────┘
       ▼
┌──────────────┐    ┌──────────────────┐
│  Agent Loop  │◄──►│  LLM (planner)   │
│  (ReAct)     │    │  gpt-4o-mini     │
└──────┬───────┘    └──────────────────┘
       │
       ├──► Tool Registry
       │      ├─ BrowserTool (Playwright chromium.launch)
       │      ├─ FileTool (sandboxed workspace)
       │      ├─ APITool (httpx → mock app)
       │      └─ AskUserTool (retry / skip / abort)
       │
       ├──► Memory (scratchpad facts + progress)
       ├──► Verifier (independent re-query + scope check)
       └──► Tracer (JSONL + screenshots)
```

## The agent loop

```python
for step in range(max_steps):
    response = await llm.chat(build_prompt(memory, tools))  # temperature=0
    if response.is_finish:
        break
    obs = await execute_with_retry(tool_call, retries=2)  # 5xx/connection only
    memory.add_step(...)
    if retries_exhausted or stuck:
        ask_user(menu=["retry", "skip", "abort"])
verification = await verifier.verify(task, memory)  # skipped on user abort
summary = build_summary(task, memory, verification)  # deterministic template
```

See `agent/loop.py`.

## Failure handling

| Signal | Behavior |
|---|---|
| HTTP **5xx** / connection error | Retry identical call up to `AGENT_RETRIES` (default 2) with backoff |
| HTTP **4xx** (validation, conflict) | **No retry** — semantic; planner must fix the request |
| Retries exhausted | Escalate: constrained menu `(r)etry / (s)kip / (a)bort` |
| No progress (≥3 idle steps) | Same menu |
| User **abort** | `status=failed`, facts preserved, verification skipped, CLI exit 0 |

`CHAOS=1` injects one 500 then recovers. `PERMANENT_FAIL=1` always 500 so the escalation path is demoable.

## Tool contracts

| Tool | Role |
|---|---|
| **api** | Structured reads/writes against the mock REST API. Primary path for speed and reliability. |
| **browser** | Real Playwright `chromium.launch()` against mock HTML (`/mail`, `/finance`, `/finance/invoices`). Used to confirm invoice UI after POST. Not `connect_over_cdp`. |
| **files** | Sandboxed JSON/CSV under `./workspace/` (path traversal blocked). |
| **ask_user** | Constrained menu: retry / skip / abort. Used on stuck or exhausted retries. |
| **remember** / **finish** | Scratchpad facts and terminal signal. |

## Verification design

The verifier does **not** trust the agent's summary:

1. **Re-derive** ground truth from mail / payslip APIs (e.g. invoice ID from source email).
2. **Confirm** system state with a separate finance/HR query.
3. **Reject scope violations** — any write not justified by the task fails (`no_out_of_scope_writes`).
4. **Skip after abort** — deliberate user abort does not re-query finance (avoids a false "verification failed").

Read-only payslip tasks must never `POST /api/invoices`.

## Design decisions (why)

| Choice | Why |
|---|---|
| Custom ReAct loop | Flexibility when reality diverges; frameworks hide the loop we're graded on |
| Separate verifier | Executors hallucinate success; only independent re-query is trustworthy |
| Mock FastAPI app | Brief forbids real credentials; still real HTTP + real DOM |
| Playwright | Auto-wait / better DX than Selenium; launches its own Chromium |
| `temperature=0` | Reduce flaky multi-step runs |
| Deterministic summary templates | No hallucinated dollar amounts in the user-facing report |
| Menu without free-text | Three actions cover the prototype; no dead "inform" branch |

Full write-up: [`DESIGN.md`](DESIGN.md).

## Demo traces (checked in)

- `traces/primary_clean.jsonl` — happy path
- `traces/primary_chaos_retry.jsonl` — real run with `HTTP 500` then recovery
- `traces/secondary_payslip.jsonl` — generalization (same loop, no finance writes)

Escalation is covered by `make escalate-demo` and `tests/test_e2e_escalation.py` (stubbed LLM + real permanent-500 mock).

## Known limitations

- Only works against the bundled mock app
- Retry and escalation are coupled: a permanently-500ing endpoint is retried like a transient blip, then escalated. Production should separate transient vs persistent failure classes before retrying.
- LLM may still skip the browser confirmation step on some runs (API path alone can satisfy the task; soft-finish waits for a browser step on invoice tasks)
- IDE/devtools may probe `localhost:8000/json/version` (Chrome CDP discovery) — that is **not** our browser tool; Playwright uses `chromium.launch()`
- No persistent memory across sessions
- Verification assumes query endpoints exist
- Single-task execution; no queueing

## What's next

- Separate transient vs persistent failure policies (retry only the former)
- Persistent vector memory across tasks
- Real Gmail/Slack read-only connectors (OAuth)
- Multi-agent split (planner / executor / verifier)
- Live step playback UI
- Cost/latency dashboard per run

## Assumptions

- OpenAI API key in `.env` (`AGENT_MODEL` defaults to `gpt-4o-mini`)
- Python 3.11+ and Playwright Chromium (`make install`)
- "Latest invoice" = newest email timestamp with a valid amount
- Mock app is trusted; no adversarial inputs

## Dependencies

See `pyproject.toml`: FastAPI, Playwright, OpenAI SDK, Pydantic v2, Typer, httpx, pytest. **No** LangChain / CrewAI / AutoGPT.

Optional UI: `uv run streamlit run ui.py` (mock app must be running).

## Tests

```bash
make test
```

Covers file sandboxing, API observations (including chaos 500→201), Playwright against the live mock app, memory/progress, ask_user menu, retry policy (4xx vs 5xx), verifier scope + ground truth, summary templates, stubbed-LLM primary E2E, and escalation abort (`PERMANENT_FAIL`).

## Pre-submit smoke check

```bash
# Fresh clone
cd /tmp && git clone https://github.com/purvanshh/Nexora.git nexora-fresh && cd nexora-fresh
cp .env.example .env   # paste OPENAI_API_KEY
make install && make test

make demo && make chaos-demo && make escalate-demo && make secondary

git ls-files | grep -E '\.env$'          # must be empty
grep -iE 'loom|youtube|video' Readme.md  # must return a line
```
