# Nexora — Autonomous AI Task Worker

A narrow intern prototype: give it a natural-language office task, and it **plans, executes real tools** against a local mock company (mail + finance + HR), **adapts on failure**, **independently verifies** the outcome, and returns a summary with evidence. Breadth is deliberately limited; every tool call does real work.

## Setup (5 commands)

```bash
git clone <repo-url> && cd Nexora
cp .env.example .env   # add OPENAI_API_KEY
make install
make demo              # boots mock app + runs primary scenario
```

Secondary scenario (same agent loop, different prompt):

```bash
make secondary   # boots mock app + payslip task (same agent loop)
```

> Do not run `uv run python cli.py ...` alone unless `make mock` is already up — the agent health-checks the mock app at startup.

Chaos / retry demo:

```bash
make chaos-demo   # CHAOS=1 injects a 500 on first invoice POST
```

## Architecture

```
┌──────────────┐
│  CLI / UI    │  ← natural language task in
└──────┬───────┘
       ▼
┌──────────────┐    ┌──────────────────┐
│  Agent Loop  │◄──►│  LLM (planner +  │
│  (ReAct)     │    │  reasoner)       │
└──────┬───────┘    └──────────────────┘
       │
       ├──► Tool Registry
       │      ├─ BrowserTool (Playwright)
       │      ├─ FileTool
       │      ├─ APITool
       │      └─ AskUserTool
       │
       ├──► Memory (scratchpad)
       ├──► Verifier (independent check)
       └──► Tracer (JSONL logs + screenshots)
```

## The agent loop

```python
for step in range(max_steps):
    response = await llm.chat(build_prompt(memory, tools))
    if response.is_finish:
        break
    obs = await execute_with_retry(tool_call, retries=2)
    memory.add_step(...)
verification = await verifier.verify(task, memory)  # independent re-query
```

See `agent/loop.py` for the full implementation.

## Tool contracts

- **browser** — Playwright against the mock HTML UI (`goto` / `click` / `fill` / `extract` / `screenshot` / `wait_for`); auto-screenshots each step.
- **files** — sandboxed read/write/list under `./workspace/` (path traversal blocked).
- **api** — `httpx` to the mock REST API; 4xx/5xx become `Observation(ok=False)`.
- **ask_user** — CLI `input()` for ambiguity, irreversible actions, or repeated failure.
- **remember** / **finish** — scratchpad facts and terminal summary.

## Verification design

Actions can lie, and agents can overstep. The verifier:

1. **Re-derives** the correct outcome from the source of truth (mail / payslip APIs) — it does not trust the agent's summary.
2. **Confirms system state** (finance record exists, net pay matches).
3. **Rejects scope violations** — any POST/write not justified by the task fails verification (`no_out_of_scope_writes`).

Read-only tasks (e.g. payslip lookup) must never create invoices.

## Design decisions

Documented in depth in [`DESIGN.md`](DESIGN.md): ReAct vs plan-and-execute, Playwright vs Selenium, custom loop vs LangChain, mock app vs real sites, failure taxonomy, cost budget.

## Demo

```bash
make demo
```

Example checked-in traces:

- `traces/primary_happy.jsonl`
- `traces/primary_with_retry.jsonl`
- `traces/secondary_payslip.jsonl`

Optional UI: `uv run streamlit run ui.py` (requires mock app running).

## Known limitations

- Only works against the bundled mock app
- LLM may hallucinate selectors — mitigated by retries but not eliminated
- No persistent memory across sessions
- Verification relies on the mock app exposing a query endpoint
- Single-task execution; no queueing or parallelism

## What's next

- Persistent vector memory for cross-task learning
- Real Gmail/Slack read-only connectors (OAuth)
- Multi-agent split (planner + executor + verifier)
- Web UI with live step playback
- Cost/latency dashboard per run

## Assumptions

- Evaluator has an OpenAI API key (`.env`)
- Playwright + Python 3.11+ available (`make install` handles Chromium)
- "Latest invoice" = most recent by email timestamp (see seed data + prompts)
- Mock app is trusted; no adversarial inputs

## Dependencies

See `pyproject.toml`. Core: FastAPI, Playwright, OpenAI SDK, Pydantic v2, Typer, httpx, structlog, pytest. **No** LangChain / CrewAI / AutoGPT.

## Tests

```bash
make test
```

E2E (`tests/test_e2e_primary.py`) stubs the LLM but exercises real tools + the live mock app.
