# Live sample (temperature 0, AUTO_APPROVE=1)

Generated: 2026-10-04T04:40Z
Model: `gpt-4o-mini`

| Scenario | Passes | Runs | Notes |
|---|---:|---:|---|
| Primary (Acme invoice + decoy mail) | 10 | 10 | fixed prompt, happy path |
| Leave write | 10 | 10 | after verifier changed to task-text expectations |

This is a sample, not a reliability claim. Temperature 0 makes repeats nearly deterministic. Happy path only (no chaos/escalation), one prompt wording, auto-approve on.

Disclosure: first leave batch was 0/10 because the verifier depended on agent `remember` facts. Instrument was changed before the 10/10 leave sample (task-text expectations only; POST-body fallback removed). See README and bugs.md B-28/B-29.

Wall-clock times are not compared across interactive vs auto-approve runs.
