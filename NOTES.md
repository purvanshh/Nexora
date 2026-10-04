# Build notes

Scaffold → mock app → tools → ReAct loop → verifier/scope → chaos → escalation → approval gate → leave write → freeze.

See [`bugs.md`](bugs.md) for the full defect log.

## Demo recording (~5 min)

1. Pitch: NL task in, agent plans and executes.
2. `HEADLESS=false make demo` — approve the POST (`a`), watch browser, read summary (embedded records).
3. Open `traces/primary_clean.jsonl` — one thought → tool → observation.
4. `make chaos-demo` — approve, point at `500 → 201`.
5. `make escalate-demo` — approve write, then **`a`** on escalate. Narrate retries → escalate → abort.
6. `make secondary` — same loop, no POST.
7. Optional: `make leave-demo` — second write type.
8. README limitations — two bullets.

## Walkthrough answers (60s each)

1. **One decision** — narrate a step from `traces/primary_clean.jsonl`.
2. **Verifier vs executor** — re-derives ground truth from mail, separately re-queries finance; checks out-of-scope writes. Independent of claims, not of the mock.
3. **Biggest weakness** — retry and escalation are still coupled for permanent 500s; next iteration classifies first.
4. **Why no LangGraph** — graded surface is the loop itself; same ideas, explicit Python in `loop.py`.
