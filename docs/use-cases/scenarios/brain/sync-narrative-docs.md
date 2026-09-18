# sync-narrative-docs — brain

Source: plugins/sulis-brain/instances/sync-narrative-docs/workflow.jsonld
Purpose: Reconcile the four narrative-doc targets (plugin.json description, marketplace.json description, CONSUMER_HOWTO, README) against canonical state: detect drift, compute expected state, apply updates, verify coherence.
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-OPTIONAL-BRANCH, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-RETRY, UC-LOOP-BUDGET, UC-FAILURE-MODES, UC-GATE-KINDS, UC-GATE-ROUTE, UC-PRECONDITION, UC-SIDE-EFFECT-CLAIM, UC-TOOL-RUNNER, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| detect-stale-references | deterministic | Greps version markers, DR refs, entity counts, lessons range across the four files → `drift-report` | none bound (prose: Bash grep) |
| compute-expected-state | deterministic | Reads foundation version/count, latest DR, last lesson, plugin versions → `expected-state` | none bound (prose: Bash + Python) |
| update-plugin-json-description | mixed | Substitutes version markers, rewrites prose, forbids future tense; never bumps version | none bound |
| update-marketplace-json-description | deterministic | Copies plugin.json description verbatim into marketplace.json | none bound (prose: jq) |
| update-consumer-howto | mixed | Rewrites entity catalogue, DR list, lessons, footer | none bound |
| update-readme-version-history | mixed | Updates schema count, entity list, version-history entry | none bound |
| verify-coherence | deterministic | Referential-integrity check, tense forbid-list, coherence constraints → `coherence-report` | none bound (prose: `/sulis-brain:check-referential-integrity`) |

No parallel starts, fan-out or joins: one initial step and a straight line with one early exit. The four update steps are strictly ordered because each reads the previous one's result (marketplace copies plugin.json).

## Routes as declared
- `detect-stale-references -> compute-expected-state` → unconditional.
- `compute-expected-state -> update-plugin-json-description [if drift-report.has_drift OR force_resweep]` → condition on `drift-report.has_drift` and `force_resweep` (not a declared input).
- `compute-expected-state -> [terminal:noop-clean] [if NOT drift-report.has_drift AND NOT force_resweep]` → same keys → terminal verdict `noop-clean`.
- `update-plugin-json-description -> update-marketplace-json-description` → unconditional.
- `update-marketplace-json-description -> update-consumer-howto` → unconditional.
- `update-consumer-howto -> update-readme-version-history` → unconditional.
- `update-readme-version-history -> verify-coherence` → unconditional.
- `verify-coherence -> [terminal:synced] [if coherence-report clean]` → condition `coherence-report.violations == []` → terminal verdict `synced`.
- `verify-coherence -> [terminal:blocked] [if coherence-report violations require manual review]` → condition on violations needing review (judgement) → terminal verdict `blocked`.
- Failure mode stale-still-present-after-sweep (retry) → re-run the failed update step with stale markers as targets; budget max 2 retries; exhaustion → manual review.
- Failure mode trigger-debounce-required (fallback) → at detect-stale-references, if the previous run finished < 60 s ago as noop-clean → `noop-clean` without scanning.
- Failure mode readme-version-history-conflict (manual-review, non-blocking) → person chooses overwrite or skip; default skip if same latest DR, overwrite if newer.
- Failure modes coherence-check-fails, version-marker-conflict (manual-review) → surface to person; blocking.
- Failure mode derivedartifact-source-missing (escalate, blocking) → bound to no step; no route.

## Scenarios
### S1 — Drift found, synced
- Inputs: trigger `post-release-merged`; files on disk mention v0.8.0 while plugin.json is v0.9.0
- Scripted: detect → `has_drift = true`; compute → expected-state; four updates succeed; verify → no violations
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-readme-version-history, verify-coherence]
- Expect gates: []
- Expect terminal: synced

### S2 — No drift
- Inputs: trigger `operator-manual-invoke`, docs current
- Scripted: detect → `has_drift = false`; `force_resweep` unset
- Expect visited: [detect-stale-references, compute-expected-state]
- Expect gates: []
- Expect terminal: noop-clean

### S3 — No drift, forced resweep
- Inputs: `force_resweep = true`
- Scripted: detect → false; all updates succeed; verify → clean
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-readme-version-history, verify-coherence]
- Expect gates: []
- Expect terminal: synced

### S4 — Coherence violation needs review
- Inputs: operator hand-edited marketplace.json after the copy
- Scripted: verify-coherence → violation (descriptions differ); person review
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-readme-version-history, verify-coherence]
- Expect gates: [coherence-check-fails review]
- Expect terminal: blocked

### S5 — Debounced second trigger
- Inputs: trigger `post-mint-completed` 30 s after a noop-clean run
- Scripted: detect-stale-references → debounce short-circuit
- Expect visited: [detect-stale-references]
- Expect gates: []
- Expect terminal: noop-clean

### S6 — Stale marker survives one sweep, retry fixes it
- Inputs: as S1
- Scripted: update-consumer-howto pass 1 leaves "DR-018" in a footer; re-run with explicit target → clean; verify → clean
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-consumer-howto, update-readme-version-history, verify-coherence]
- Expect gates: []
- Expect terminal: synced

### S7 — Retry budget exhausted
- Inputs: as S1
- Scripted: update-consumer-howto leaves stale markers on 3 runs (1 + 2 retries); manual review
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-consumer-howto, update-consumer-howto, ...]
- Expect gates: [stale-still-present manual review]
- Expect terminal: blocked (best reading; the failure mode says escalate to manual review without naming a verdict or where the run continues)

### S8 — README entry already exists, person says skip
- Inputs: as S1, README already has an entry for the current version
- Scripted: update-readme-version-history → conflict; person → skip; verify → clean
- Expect visited: [detect-stale-references, compute-expected-state, update-plugin-json-description, update-marketplace-json-description, update-consumer-howto, update-readme-version-history, verify-coherence]
- Expect gates: [readme-version-history-conflict → skip]
- Expect terminal: synced

### S9 — Canonical source missing
- Inputs: a DerivedArtifact `derived_from` names a renamed entity
- Scripted: compute-expected-state cannot resolve its source
- Expect visited: [detect-stale-references, compute-expected-state] (best reading)
- Expect gates: []
- Expect terminal: UNSTATED (escalate, blocking; failure mode bound to no step, no route)

## Ambiguities for the process owner
- `force_resweep` is read by a route but is not declared anywhere.
- Step outputs are prose ("plugin.json description updated") that do not match the `state_contract` keys (`plugin-json-description-updated:bool`); the updates' own success is never routed on.
- verify-coherence has no route for "violations that do not require manual review"; the split between the two routes is a judgement.
- The stale-marker retry names a "follow-up scan" that is not a step; which step detects it and how control returns to the failed update step are unstated. The workflow description says v0.1.0 has no cycles.
- Four failure modes are manual review or escalate, but there is no gate step; which verdict follows the person's decision is unstated except where noted above.
- trigger-debounce-required is a route to `noop-clean` from the first step, stated only in failure-mode prose, and needs a host read of previous run completion times (undeclared ambient input).
- derivedartifact-source-missing is bound to no step.
- No tools: every step's mechanism is prose (Bash, jq, a skill invocation), so no runner exists and a validator should reject the steps.
- `verify-coherence` is the only terminal step, but `compute-expected-state` also ends the run.
- Each update step writes a file with no claim or idempotency; a concurrent second trigger could interleave writes (the debounce only covers the noop-clean case).
