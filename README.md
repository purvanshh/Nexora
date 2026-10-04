# Nexora: Autonomous AI Task Worker

A narrow intern prototype: give it a natural-language office task, and it plans, executes real tools against a local mock company (mail + finance + HR), retries transient failures, asks before writes, clarifies when the request is ambiguous, escalates when it cannot safely proceed, re-checks outcomes against the mock APIs (including scope), and returns a concise business summary with embedded evidence records.

> A narrow prototype that genuinely works beats a broad system where most functionality is mocked.

## Demo video

**[Watch the walkthrough](https://drive.google.com/drive/folders/1yz5ZYBMtdx6RqCuQBd87ZDCGW2o-jGrZ?usp=sharing)** (~5 min): primary demo, trace, chaos retry, escalation/abort, secondary, limitations.

If the recording predates the approval gate or leave demo, treat the live `make` targets as source of truth until an updated cut is linked.

## Setup (5 commands)

```bash
git clone https://github.com/purvanshh/Nexora.git && cd Nexora
cp .env.example .env          # set OPENAI_API_KEY
make install                  # deps + Playwright Chromium
make demo                     # boots mock app + primary scenario
make test                     # tools + verifier + stubbed E2E
```

Write demos pause before any POST with the exact payload. Type `a` (approve) or `r` (reject).

For a non-interactive skim (CI or reviewers):

```bash
AUTO_APPROVE=1 make demo
AUTO_APPROVE=1 make leave-demo
```

## Demo scenarios

| Target | What it proves |
|---|---|
| `make demo` | Happy path: mail, extract, approve, POST invoice, optional UI confirm |
| `make chaos-demo` | `CHAOS=1`: first invoice POST returns 500, retry then 201 |
| `make escalate-demo` | `PERMANENT_FAIL=1`: approve once, every POST 500, escalate, type `a` to abort |
| `make secondary` | Payslip lookup; same loop, no finance writes |
| `make leave-demo` | Second write task: POST `/api/leave` (approve gate + leave verifier) |

Visible browser (Playwright launches its own Chromium, not CDP against the mock app):

```bash
HEADLESS=false make demo
```

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
       │      └─ AskUserTool (approve/reject, retry/skip/abort, free-text clarify)
       │
       ├──► Memory (scratchpad facts + progress)
       ├──► Verifier (API re-query + scope check)
       └──► Tracer (JSONL + screenshots)
```

## The agent loop

```python
for step in range(max_steps):
    response = await llm.chat(build_prompt(memory, tools))  # temperature=0
    if response.is_finish:
        break
    if mutating_api and require_write_approval:
        ask_user(menu=["approve", "reject"])  # shows exact payload
    obs = await execute_with_retry(tool_call, retries=2)  # 5xx only; invoice 409→recover
    memory.add_step(...)
    if retries_exhausted or stuck:
        ask_user(menu=["retry", "skip", "abort"])
    # Ambiguity: planner may call ask_user(options=[]) for free-text clarification
verification = await verifier.verify(task, memory)  # skipped on user stop
summary = build_summary(task, memory, verification)  # templates + embedded records
```

See `agent/loop.py`. Bug history and fixes: [`bugs.md`](bugs.md).

## Failure handling

| Signal | Behavior |
|---|---|
| Before any POST/PUT/PATCH/DELETE | Approve/reject gate with exact JSON payload (`REQUIRE_WRITE_APPROVAL=1`) |
| Ambiguous task (0 or 2+ senders, missing fields) | Free-text `ask_user` with `options=[]` |
| HTTP 5xx / connection error | Retry up to `AGENT_RETRIES`; invoice may recover via matching GET |
| HTTP 409 on invoice_id | Idempotent recover via GET (safe duplicate of own invoice write) |
| HTTP 4xx validation | No retry: semantic; planner must fix the request |
| Retries exhausted | Escalate: `(r)etry / (s)kip / (a)bort` |
| User abort / reject | `status=failed`, facts preserved, verification skipped |

## Tool contracts

| Tool | Role |
|---|---|
| **api** | Primary path for structured reads/writes against the mock REST API. |
| **browser** | Optional UI confirmation after invoice POST (`goto /finance/invoices`). Real Playwright `chromium.launch()`, not computer-use automation of the whole task. The model may skip it on some runs; soft-finish waits for it on invoice tasks. |
| **files** | Sandboxed JSON/CSV under `./workspace/` (path traversal blocked). |
| **ask_user** | Menus for approve/reject and retry/skip/abort; empty `options=[]` for free-text clarification. |
| **remember** / **finish** | Scratchpad facts and terminal signal. |

## Verification design

The verifier does not trust the agent's summary text:

1. Re-derive expected values from source APIs (mail / payslip / leave list).
2. Confirm system state with a separate query.
3. Reject scope violations (`no_out_of_scope_writes`).
4. For leave, require **exactly one** matching record (duplicates fail).
5. Skip after user abort/reject.

This is independent of the **executor's claims**, not independent of the mock app. If the mock is wrong, the verifier can be wrong too. It is a second opinion against the same system under test.

Summaries embed compact JSON snapshots of the source and target records so evidence survives after localhost URLs die.

### Adding a new write task

Honest answer: you extend three places, then add a Make target + stubbed E2E test.

1. Mock route under `mock_app/routers/` (+ seed JSON if needed).
2. `classify_task` + `scope_allows` + a `_verify_*` method in `agent/verifier.py`.
3. Summary branch in `agent/summary.py` and a few lines in `prompts/system.md`.

The loop, approval gate, retries, and ask_user menus are shared. See `make leave-demo` / `tests/test_e2e_leave.py` as the template.

## Design decisions (why)

| Choice | Why |
|---|---|
| Custom ReAct loop | Flexibility when reality diverges; frameworks hide the loop we're graded on |
| Separate verifier | Executors hallucinate success; re-query catches empty DBs and scope bugs |
| Pre-write approval | Finance/HR writes need a human gate, not only post-failure escalation |
| Free-text clarify | Menus alone cannot resolve "which sender?" when zero or multiple match |
| Mock FastAPI app | Brief forbids real credentials; still real HTTP + real DOM |
| API-first + light browser | Structured tools are reliable; browser confirms UI, it does not drive the whole task |
| Deterministic summary templates | No hallucinated dollar amounts; records embedded inline |
| Client invoice_id + 409 recover | Makes invoice POST retries safer under ambiguous 500s |

Full write-up: [`DESIGN.md`](DESIGN.md).

## Demo traces (checked in)

- `traces/primary_clean.jsonl`: happy path
- `traces/primary_chaos_retry.jsonl`: real run with HTTP 500 then recovery
- `traces/secondary_payslip.jsonl`: generalization (same loop, no finance writes)

Seed mail includes an older Acme invoice, a malformed Acme reminder, and an **Acme Corporation** decoy so "latest Acme Corp" is not trivial.

## Live reliability sample

Run with `make reliability` (`AUTO_APPROVE=1`, temperature 0). Sample from 2026-10-04 (`traces/reliability_20261004.md`):

| Scenario | Passes | Runs | Notes |
|---|---:|---:|---|
| Primary (Acme invoice + decoy mail) | 10 | 10 | decoy sender present in seed |
| Leave write | 10 | 10 | verifier accepts POST body / task dates when scratchpad remember is skipped |

Wall-clock times are not compared across interactive vs auto-approve runs (human typing at the approve prompt is not agent latency).

## Known limitations

- Only works against the bundled mock app
- Invoice POST retries can recover via client `invoice_id` + 409/GET. Leave IDs are server-generated, so a committed-but-500 leave POST can still duplicate on retry. Production fix: idempotency keys at the API layer. The leave verifier fails if more than one matching record exists.
- Retry and escalation are still coupled for permanent 500s (retry N times, then ask)
- Verifier deep checks are task-kind templates (invoice / payslip / leave); unknown tasks fail closed
- Browser confirmation is secondary and sometimes skipped by the model
- IDE/devtools may probe `localhost:8000/json/version` (not our browser tool)
- No persistent memory across sessions; single-task execution

## What's next

- Idempotency keys on all write endpoints (not only invoice_id)
- Separate transient vs persistent failure policies before retrying
- Generic verifier hooks so new write tasks need less hand-written Python
- Real Gmail/Slack read-only connectors (OAuth)
- Live step playback UI

## Assumptions

- OpenAI API key in `.env` (`AGENT_MODEL` defaults to `gpt-4o-mini`)
- Python 3.11+ and Playwright Chromium (`make install`)
- "Latest invoice" = newest email timestamp from the exact requested sender with a valid amount
- Mock app is trusted for this prototype; no adversarial inputs

## Dependencies

See `pyproject.toml`: FastAPI, Playwright, OpenAI SDK, Pydantic v2, Typer, httpx, pytest. No LangChain / CrewAI / AutoGPT / LangGraph.

Why no framework: the graded surface is the loop (plan, tool, observe, retry, escalate, verify). A graph library would hide the code reviewers ask you to walk through. Same ideas as LangGraph, just explicit Python in `agent/loop.py`.

Optional UI: `uv run streamlit run ui.py` (mock app must be running).

## Tests

```bash
make test
```

Covers sandboxing, API/chaos, Playwright against the live mock, ask_user menus and free-text clarify, write approval, auto-approve, idempotent invoice POST recover, leave uniqueness, retry policy, verifier scope, leave write E2E, primary E2E, and escalation abort.
