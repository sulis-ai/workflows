# prove — brain

Source: plugins/sulis-brain/instances/prove/workflow.jsonld
Purpose: Prove a delivered change is really built by naming its critical scenarios, actually running them, opening the saved output, and returning an observed-or-blocked verdict per scenario.
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-OUT-TYPED, UC-MECHANISM, UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-TOOL-RUNNER, UC-CAPABILITY, UC-PRECONDITION, UC-CRITICALITY, UC-FAILURE-MODES, UC-STOP-NAMED, UC-STOP-HONEST, UC-FIDELITY, UC-CALL (as a callee of change-lifecycle), UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| find-critical-scenarios | mixed | Names critical user journeys and production mechanisms, each with a real drivable interface and observable pass condition → `critical-scenarios` | none (pure agent reasoning) |
| drive-reality-check | deterministic | Actually runs the standing suite / real flow, no stubs → `drive-results` | needs `reality-check-execution` → run-reality-check (subprocess `prove_reality_check_cli {branch_name}`, side-effect) |
| inspect-saved-output | deterministic | Opens saved artifacts and compares content to pass conditions → `inspection-record` | needs `saved-output-inspection` → inspect-saved-artifact (subprocess `inspect_saved_artifact_cli {branch_name} {critical_scenarios}`, query) |
| render-verdict | mixed | Joins both records into per-scenario observed/blocked and overall proven/blocked → `prove-verdict` | none |

No parallel starts, fan-out or joins: a straight line of four steps. Per-scenario work happens inside each tool, not as a declared for-each.

## Routes as declared
- `find-critical-scenarios -> drive-reality-check [the critical scenarios are named ... — critical-scenarios exists and each names a real interface that can be driven]` → unconditional in practice; the bracket is a postcondition, not a branch. No route when it fails.
- `drive-reality-check -> inspect-saved-output [the reality check was RUN for real against the real interface ... — drive-results holds the real execution result]` → unconditional; postcondition only.
- `inspect-saved-output -> render-verdict [the actual saved artifacts were OPENED + inspected (not trusted) — inspection-record holds what was observed ...]` → unconditional; postcondition only.
- `render-verdict -> [terminal:proven] [an observed-or-blocked verdict is emitted per scenario as prove-verdict ... — the subject is proven observed-or-blocked]` → terminal verdict `proven` regardless of `prove-verdict.overall`.

## Scenarios
### S1 — Every scenario observed
- Inputs: `subject-ref = "dna:change:... (CSV export feature)"`, `branch_name = "feat/csv-export"`
- Scripted: find-critical-scenarios → 3 scenarios (export journey, persistence, auth); drive-reality-check → exit 0, all driven, artifact paths; inspect-saved-output → all opened, all match; render-verdict → overall `proven`
- Expect visited: [find-critical-scenarios, drive-reality-check, inspect-saved-output, render-verdict]
- Expect gates: []
- Expect terminal: proven (`prove-verdict.overall = proven`)

### S2 — A scenario cannot be driven
- Inputs: as S1
- Scripted: drive-reality-check → persistence scenario `driven = false`; inspect → that artifact `opened = false`; render-verdict → that scenario blocked, overall `blocked`
- Expect visited: [find-critical-scenarios, drive-reality-check, inspect-saved-output, render-verdict]
- Expect gates: []
- Expect terminal: proven (the only declared terminal; `prove-verdict.overall = blocked`)

### S3 — Ran without error but saved output is a stub
- Inputs: as S1
- Scripted: drive → exit 0; inspect → export file contains a hardcoded fixture, `stub_or_fake_flag = true`, `matches_pass_condition = false`; render-verdict → blocked
- Expect visited: [find-critical-scenarios, drive-reality-check, inspect-saved-output, render-verdict]
- Expect gates: []
- Expect terminal: proven (`prove-verdict.overall = blocked`, `stubs_flagged` non-empty)

### S4 — Observation step approximated instead of run
- Inputs: as S1
- Scripted: drive-reality-check produces a narrated result with no real subprocess (failure mode assumed-instead-of-observed, escalate, blocks progress)
- Expect visited: [find-critical-scenarios, drive-reality-check] then a re-run of drive-reality-check as a real dispatch (best reading), then [inspect-saved-output, render-verdict]
- Expect gates: []
- Expect terminal: proven if the re-run succeeds; UNSTATED if escalation stops the run (no escalation route or budget)

### S5 — Wrong or missing critical scenarios
- Inputs: `subject-ref` whose context names no drivable interface
- Scripted: find-critical-scenarios → scenarios without real interfaces (failure mode wrong-or-missing-critical-scenarios, manual-review, does not block)
- Expect visited: [find-critical-scenarios, drive-reality-check, inspect-saved-output, render-verdict] (best reading: non-blocking, the run continues)
- Expect gates: [] (manual review is declared but no gate step exists)
- Expect terminal: proven (`overall = blocked` expected, since scenarios cannot be driven)

## Ambiguities for the process owner
- There is one terminal verdict, `proven`, even when `prove-verdict.overall == blocked`. change-lifecycle routes on `prove-verdict == blocked`, so the real outcome lives in an output field, not the verdict.
- Transition brackets are postconditions, not conditions; a step that fails its postcondition has no route.
- Tool arguments `{branch_name}` and `{critical_scenarios}` are not state keys; only `subject-ref` is declared. How `branch_name` is derived from `subject-ref` is unstated.
- `inspect-saved-output` is described as a `claude_code_tool` (glob + read_file) but its tool is `subprocess`; the step text is stale.
- `find-critical-scenarios` and `render-verdict` are labelled `mixed` but described as pure agent reasoning.
- Two manual-review failure modes and one escalate failure mode have no gate step, route, or retry budget.
- `prove-verdict` has a stated dict shape, but no schema is declared, so the output cannot be checked before it is recorded.
- The per-scenario join in render-verdict relies on scenario names matching across two records; no key is declared.
