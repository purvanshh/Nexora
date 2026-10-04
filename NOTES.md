# Build notes

Scaffold → mock app → tools → ReAct loop → verifier/scope → chaos → escalation (Path A) → freeze.

## Demo recording (~5 min)

1. Pitch: NL task in, agent plans and executes.
2. `HEADLESS=false make demo` — watch browser, read summary.
3. Open `traces/primary_clean.jsonl` — one thought → tool → observation.
4. `make chaos-demo` — point at `500 → 201`.
5. `make escalate-demo` — type **`a`** on the menu. Narrate: retries → escalate → abort → facts preserved → verify skipped.
6. `make secondary` — same loop, no POST.
7. README limitations — two bullets.

## Walkthrough answers (60s each)

1. **One decision** — narrate a step from `traces/primary_clean.jsonl`.
2. **Verifier vs executor** — re-derives ground truth from mail, separately re-queries finance; also checks out-of-scope writes.
3. **Biggest weakness** — retry and escalation are coupled; permanent 500 is retried like transient. Next iteration: classify first, escalate persistent failures immediately.
