# design-data-contract — brain

Source: plugins/sulis-brain/instances/design-data-contract/workflow.jsonld
Purpose: Produce one faithfully-grounded design artifact (an engineer-facing data contract) by dispatching compile-manifest then the faithful-generation-harness, with a gate that refuses to land unless both ran.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-OUT-MODE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-VERDICT-ROUTE, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-CALL, UC-FAILURE-MODES, UC-PRECONDITION, UC-CRITICALITY, UC-TOOL-KINDS, UC-MECHANISM, UC-TRIGGER, UC-FIDELITY

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| scope-artifact | mixed | Record the five plug-ins (data-contract values: ADR-001, design brief, CF-03/CF-04, CP-01; audience "consumer seam only") | — |
| compile-manifest | deterministic | Dispatch manifest compilation → `manifest`, `compile-manifest-run-id` | dispatch-compile-manifest (workflow_dispatch → `compile-manifest`, dna:workflow:01KV45DBCW7SVNPYHEHCFMJNH9, via `/sulis-brain:execute-workflow`) |
| generate-faithful | deterministic | Dispatch grounded generation → `generated-artifact`, `binding-table`, `harness-verdict`, `harness-run-id` | dispatch-harness (workflow_dispatch → `faithful-generation-harness`, dna:workflow:01KT3GM8ZF8PC7RJSGSE5JE7QQ) |
| land-and-verify | mixed | Enforcement gate: both run ids + verdict; land binding table as CONTRACT_FIRST claim entries → `generated-artifact`, `both-run-ids-present`, `final-verdict` | — |

## Routes as declared
- `scope-artifact -> compile-manifest` → unconditional.
- `compile-manifest -> generate-faithful [if the dispatched compile-manifest run returned final-verdict==manifest-ready WITH a run_id captured into compile-manifest-run-id]` → condition child `final-verdict == manifest-ready AND compile-manifest-run-id present`.
- `compile-manifest -> [terminal:blocked] [if the dispatched compile-manifest run returned sources-insufficient — escalate to the caller to supply additional declared-sources; do NOT proceed to generation against an empty/leaky manifest]` → condition child `sources-insufficient` → terminal `blocked`.
- `generate-faithful -> land-and-verify [if the dispatched faithful-generation-harness run returned a terminal verdict (grounded|partial-unattributed|manifest-insufficient) WITH a run_id captured into harness-run-id]` → condition `harness-verdict ∈ enum AND harness-run-id present`.
- `generate-faithful -> [terminal:blocked] [if the faithful-generation-harness sub-workflow is UNRESOLVABLE (sibling instance not found) — dispatch-unresolvable FailureMode fires; emit a BLOCKER and never hand-author the artifact (platform-contract ADR-004 precedent)]` → call-resolution failure → terminal `blocked`.
- `land-and-verify -> [terminal:artifact-produced] [if both-run-ids-present==true (compile-manifest-run-id AND harness-run-id both captured) AND harness-verdict in {grounded, partial-unattributed}]` → terminal `artifact-produced`.
- `land-and-verify -> compile-manifest [if harness-verdict==manifest-insufficient AND the named missing variables can be covered by additional declared-sources — re-compile with the augmented source set]` → loop back; second clause UNSTATED in state; budget UNSTATED.
- `land-and-verify -> [terminal:blocked] [if harness-verdict==manifest-insufficient and the missing variables cannot be sourced, OR both-run-ids-present==false (the enforcement gate caught a step that did not dispatch) — run-id-missing FailureMode fires]` → terminal `blocked`.

## Scenarios
### S1 — grounded contract
- Inputs: `artifact-type: "data contract"`, `generation-goal: "engineer-facing data contract for the SessionManager seam"`, `declared-sources: [{kind: adr, ref: ADR-001}, {kind: convention, ref: CF-03}]`, `artifact-audience: "consumer seam only"`, `landing-format: "CONTRACT_FIRST claim-entry block"`
- Scripted: compile-manifest → `manifest-ready` R1; faithful-generation-harness → `grounded` R2
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S2 — partial-unattributed
- Inputs: as S1
- Scripted: harness → `partial-unattributed` R2
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→partial-unattributed], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S3 — sources insufficient
- Inputs: as S1 with dangling refs
- Scripted: compile-manifest → `sources-insufficient`
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→sources-insufficient]]
- Expect gates: []
- Expect terminal: blocked

### S4 — harness unresolvable
- Inputs: as S1
- Scripted: harness target instance not found; dispatch-unresolvable fires
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful]
- Expect gates: []
- Expect terminal: blocked

### S5 — manifest insufficient, augmented once
- Inputs: as S1
- Scripted: harness pass 1 → `manifest-insufficient` naming missing variables (augmentable); compile-manifest pass 2 with added source → `manifest-ready` R3; harness pass 2 → `grounded` R4
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→manifest-insufficient], land-and-verify, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S6 — manifest insufficient, cannot be sourced
- Inputs: as S1
- Scripted: harness → `manifest-insufficient`; missing variables have no source
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→manifest-insufficient], land-and-verify]
- Expect gates: []
- Expect terminal: blocked

### S7 — inline bypass caught
- Inputs: as S1
- Scripted: `compile-manifest-run-id` absent at land-and-verify (a step did not dispatch); run-id-missing fires (abort)
- Expect visited: [scope-artifact, compile-manifest, generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]  (reachable only if compile-manifest's run-id check was bypassed)
- Expect gates: []
- Expect terminal: blocked

### S8 — augmentation never converges
- Inputs: as S1
- Scripted: harness → `manifest-insufficient` (augmentable) every pass
- Expect visited: [scope-artifact, (compile-manifest, generate-faithful, land-and-verify) repeated — no budget]
- Expect gates: []
- Expect terminal: UNSTATED

## Ambiguities for the process owner
- The augment loop has no budget; "can be covered by additional declared-sources" has no state key; who supplies the augmented `declared-sources` (a person? the harness's named gaps?) is unstated — the sources-insufficient route says "escalate to the caller", implying an input gate that is not declared.
- The harness can stop on a person (false-citation / grounding-check-theatre, manual-review, blocking) without a verdict; no route here.
- scope-artifact both reads and overwrites the five plug-ins with fixed data-contract values; whether caller-supplied values win is unstated.
- The run-id-missing route is effectively unreachable if the two preceding route conditions are enforced; its meaning as an "inline bypass" detector depends on the engine not enforcing them.
- The workflow is structurally identical to design-work-package (only plug-in values differ); a template with parameters is implied but not declared.
- Failure modes have no recovery_detail; run-id-missing is `abort` yet routes to a named terminal.
