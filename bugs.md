# Bugs log — what broke, how we fixed it

Living list of defects found while building Nexora, including the pre-submit review findings. Newest issues first within each section.

## Consistency pass (post-approval-gate review)

### B-28 — Leave live runs 0/10: POST ok but verifier had no facts
**Symptom:** Model posted the correct leave body then finished without `remember`; verifier compared `None` dates and failed every AUTO_APPROVE leave run.  
**Fix:** Resolve leave expected fields from scratchpad, then successful POST body, then task text. Summary uses the same expected fields. Prompt still asks to remember before finish.

### B-27 — Interactive `make demo` blocked reviewers
**Symptom:** Write approval made demos require a TTY.  
**Fix:** `AUTO_APPROVE=1` answers approve on write gates (`AskUserTool.auto_approve`). Documented in README and Make.

### B-26 — Clarification missing from human-in-the-loop surface
**Symptom:** Only menus existed; brief asks for clarification on ambiguity.  
**Fix:** `ask_user` with `options=[]` is free-text mode; system prompt tells the planner to clarify on 0/2+ senders.

### B-25 — Leave verifier accepted duplicates
**Symptom:** Existence check passed even if retry created two identical leave rows.  
**Fix:** Leave verification requires exactly one matching record (`tests/test_leave_verifier.py`).

### B-24 — 409 recovery overclaimed for all writes
**Symptom:** Design text implied POST retries were generally safe; leave IDs are server-minted.  
**Fix:** Limitations + DESIGN call out invoice-only idempotent recover; leave needs API idempotency keys.

### B-23 — README had internal smoke checklist / em dashes / Readme casing
**Symptom:** Pre-submit block in public docs; AI-looking punctuation; `Readme.md` vs `README.md`.  
**Fix:** Moved smoke to `scripts/smoke_check.sh`; cleaned prose; standardized on `README.md`.

## Live demo warts

### B-22 — Leave POST used scratchpad keys (`leave_start`) → 422
**Symptom:** `make leave-demo` approved a payload with `leave_start` / `leave_end` / `leave_reason`, got HTTP 422, then recovered with `start_date` / `end_date` / `reason` on a second approve. Task still succeeded.  
**Fix:** System + plan prompts now state the API body must use `start_date` / `end_date` / `reason` only; remember keys stay in the scratchpad.

## Pre-submit review (attack surface)

### B-21 — No approval gate before finance writes
**Symptom:** Agent could POST invoices after failures only; brief asks for approval/clarification when it cannot safely proceed, and a write to finance with no pre-write gate is an easy review fail.  
**Fix:** `REQUIRE_WRITE_APPROVAL` (default on). Before any mutating API call the loop shows method, path, and exact JSON and asks `(a)pprove / (r)eject`. Identical approved payloads are not re-prompted on retries. Covered by `tests/test_approval_gate.py`.

### B-20 — Generalization looked per-task and read-only
**Symptom:** Secondary demo was only a payslip GET; README did not say what to change for a new write task.  
**Fix:** Added HR leave write path (`POST /api/leave`), leave verifier/scope/summary, `make leave-demo`, and `tests/test_e2e_leave.py`. README now documents the three extension points honestly.

### B-19 — Browser oversold as computer use
**Symptom:** Logs showed a single `goto /finance/invoices` after the API write; README sounded like full browser automation.  
**Fix:** Reworded README/DESIGN/system prompt: API-first, browser is optional UI confirmation, soft-finish still waits for a browser step on invoice tasks.

### B-18 — Blind POST retries are unsafe
**Symptom:** If a write commits but the client sees 500/timeout, retry can duplicate; 409 then looks like failure on a successful write.  
**Fix:** Client-supplied `invoice_id` + idempotent recover: on 409 or 5xx, GET by id and treat a matching record as success (`idempotent_recover`). Tests in `tests/test_idempotent_recover.py`.

### B-17 — "Independent verifier" overclaim
**Symptom:** Docs said only independent re-query is trustworthy, which fails if the mock itself is wrong.  
**Fix:** Softened language: independent of the *executor's claims*, still depends on the system under test.

### B-16 — "Latest Acme" was too easy / weak reliability story
**Symptom:** Few Acme mails; similar senders could confuse; temperature 0 runs are not a reliability study.  
**Fix:** Seed decoy `Acme Corporation` (ACM-900) plus older Acme invoice and malformed reminder; mail sender filter is exact match. README states we do not claim 10/10 live pass rate.

### B-15 — Evidence was dead localhost URLs
**Symptom:** Summary/evidence listed `http://localhost:8000/...` which dies when the server stops.  
**Fix:** Summaries embed compact JSON snapshots of source/target records; API observations also attach `record:{...}` evidence.

### B-14 — Dead `(i)nform` branch
**Symptom:** Escalation menu offered inform, then immediately re-prompted with no free-text input.  
**Fix:** Removed inform. Menu is retry / skip / abort only (Fix B). Escalation copy no longer claims "transient" under `PERMANENT_FAIL`.

## Runtime / demo bugs while building

### B-13 — Escalate demo exited non-zero / verify after abort
**Symptom:** `make escalate-demo` returned Error 1; verifier re-queried finance after abort and looked like a second failure.  
**Fix:** Skip verification on user abort/reject (`method=skipped_abort`). CLI exits 0 when `user_aborted` (expected escalate path).

### B-12 — Permanent failure path missing
**Symptom:** Chaos only proved one 500 then success; escalation after exhausted retries was unproven.  
**Fix:** `PERMANENT_FAIL=1` on finance POST, `make escalate-demo`, stubbed E2E `tests/test_e2e_escalation.py`.

### B-11 — HTTP 422 retried three times (missing sender)
**Symptom:** Agent POSTed without `sender`, got 422, retry policy treated it like transient and burned retries.  
**Fix:** `is_retryable` only for 5xx/connection. 4xx returns immediately so the planner can fix the payload. Prompt requires all four invoice fields before POST. `tests/test_retry_policy.py`.

### B-10 — Wrong / invented invoice IDs in summary
**Symptom:** Finance minted IDs or summary showed `unknown` / mismatched INV-* vs mail.  
**Fix:** Honor client `invoice_id` on create; 409 on conflict; verifier checks finance id == source mail id; summary always uses scratchpad `invoice_id`.

### B-09 — Soft-finish printed raw dicts
**Symptom:** User-facing summary looked like a Python dict dump.  
**Fix:** Deterministic templates in `agent/summary.py` (no second LLM call for numbers).

### B-08 — `/json/version` noise / CDP confusion
**Symptom:** Logs and reviewers thought we attached to the mock via Chrome DevTools Protocol.  
**Fix:** Documented and kept `chromium.launch()` only. `/json/version` probes come from IDE/devtools, not our tool.

### B-07 — Chaos mode never fired in `make chaos-demo`
**Symptom:** `.env` had `CHAOS=0` and overwrote the Make-exported `CHAOS=1`.  
**Fix:** Load `.env` from repo-root absolute path; process env for chaos/permanent-fail is read per-request in the mock; Make exports win when set before process start. Demo script preserves caller env for those flags.

### B-06 — Stuck planner (prose, no tool call)
**Symptom:** Model replied with plain text and the loop spun.  
**Fix:** OpenAI calls use `tool_choice="required"`; empty tool calls become a failed observation and can escalate.

### B-05 — Secondary demo / some Make targets without mock server
**Symptom:** Agent hit connection errors because uvicorn was not started.  
**Fix:** All agent Make targets go through `scripts/run_demo.sh` for consistent mock lifecycle + seed reset.

### B-04 — Secondary wrote an invoice (scope leak)
**Symptom:** Payslip task POSTed `/api/invoices`.  
**Fix:** System prompt scope rules + verifier `no_out_of_scope_writes` inspecting the mutation log.

### B-03 — Missing OpenAI credentials despite `.env`
**Symptom:** CLI said key missing when cwd was wrong or `.env` was not found.  
**Fix:** Settings always load `.env` from repo root (`Path(__file__).parent.parent`), not process cwd.

### B-02 — `run_demo.sh` broke on apostrophe in default task
**Symptom:** Bash quoting around `it's` / heredoc blew up the demo script.  
**Fix:** Default task owned by CLI/Make strings; script passes the task argument through safely.

### B-01 — Scaffold / early integration flakes
**Symptom:** Path traversal in files tool, empty finance after "success", flaky selectors.  
**Fix:** Sandboxed `FileTool`, verifier re-query, Playwright auto-wait + simple `goto` confirmation rather than brittle form scripting as the primary path.

## Still open (documented, not pretend-fixed)

- Retry vs escalation still coupled for permanent 500s (retry N times, then ask).
- Deep verifier is still task-kind templates; fully generic verification is future work.
- Live LLM pass-rate table (10× runs) not checked into the repo.
- Free-text clarification is intentionally out of scope; menus only.
