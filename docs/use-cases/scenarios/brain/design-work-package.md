# design-work-package — brain

Source: plugins/sulis-brain/instances/design-work-package/workflow.jsonld
Purpose: Meta-workflow producing a Work Package: scope the artifact, dispatch compile-manifest, dispatch the faithful-generation-harness, and land the result only when both run ids are present and the harness verdict is grounded or partial-unattributed.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-OUT-MODE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-VERDICT-ROUTE, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-CALL, UC-FAILURE-MODES, UC-PRECONDITION, UC-CRITICALITY, UC-TOOL-KINDS, UC-MECHANISM, UC-TRIGGER, UC-FIDELITY

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| scope-artifact | mixed | Record the five plug-ins (artifact-type, generation-goal, artifact-audience, declared-sources, landing-format) with fixed Work Package values | — |
| compile-manifest | deterministic | Dispatch manifest compilation → `manifest`, `compile-manifest-run-id` | dispatch-compile-manifest (workflow_dispatch → `compile-manifest`, dna:workflow:01KV45DBCW7SVNPYHEHCFMJNH9) |
| generate-faithful | deterministic | Dispatch grounded generation → `generated-artifact`, `binding-table`, `harness-verdict`, `harness-run-id` | dispatch-harness (workflow_dispatch → `faithful-generation-harness`, dna:workflow:01KT3GM8ZF8PC7RJSGSE5JE7QQ) |
| land-and-verify | mixed | Gate on both run ids + verdict; render binding table as WP markdown → `generated-artifact`, `both-run-ids-present`, `final-verdict` | — |

## Routes as declared
- `scope-artifact -> compile-manifest` → unconditional.
- `compile-manifest -> generate-faithful [if dispatched compile-manifest returned manifest-ready WITH a run_id captured]` → condition child verdict `manifest-ready AND compile-manifest-run-id present`.
- `compile-manifest -> [terminal:blocked] [if dispatched compile-manifest returned sources-insufficient]` → condition child verdict `sources-insufficient` → terminal `blocked`.
- `generate-faithful -> land-and-verify [if dispatched harness returned a terminal verdict WITH a run_id captured]` → condition `harness-verdict` set AND `harness-run-id` present.
- `generate-faithful -> [terminal:blocked] [if the harness sub-workflow is UNRESOLVABLE — dispatch-unresolvable fires; BLOCKER, never hand-author]` → failure (dispatch-unresolvable) → terminal `blocked`.
- `land-and-verify -> [terminal:artifact-produced] [if both-run-ids-present AND harness-verdict in {grounded, partial-unattributed}]` → condition → terminal `artifact-produced`.
- `land-and-verify -> compile-manifest [if harness-verdict==manifest-insufficient AND missing variables can be covered by more sources]` → loop back to compile-manifest; second clause UNSTATED in state; budget UNSTATED.
- `land-and-verify -> [terminal:blocked] [if harness-verdict==manifest-insufficient with no augmentable sources, OR both-run-ids-present==false — run-id-missing fires]` → terminal `blocked`.

## Scenarios
### S1 — grounded Work Package
- Inputs: `declared-sources: [{kind: note, ref: "WP-03 TDD slice"}, {kind: note, ref: "design WHY"}, {kind: convention, ref: WORK_PACKAGE_STANDARD}]` (other four plug-ins set by scope-artifact)
- Scripted: compile-manifest → `manifest-ready`, run_id R1; faithful-generation-harness → `grounded`, run_id R2; land-and-verify → both present
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S2 — partial-unattributed still produced
- Inputs: as S1
- Scripted: harness → `partial-unattributed`
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→partial-unattributed], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S3 — sources insufficient
- Inputs: as S1
- Scripted: compile-manifest → `sources-insufficient`
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→sources-insufficient]]
- Expect gates: []
- Expect terminal: blocked

### S4 — harness unresolvable
- Inputs: as S1
- Scripted: dispatch-harness cannot resolve its target; dispatch-unresolvable fires
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful]
- Expect gates: []
- Expect terminal: blocked

### S5 — manifest insufficient, augmented once
- Inputs: as S1
- Scripted: harness pass 1 → `manifest-insufficient` (augmentable); compile-manifest pass 2 → `manifest-ready` R3; harness pass 2 → `grounded` R4
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→manifest-insufficient], land-and-verify, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]
- Expect gates: []
- Expect terminal: artifact-produced

### S6 — manifest insufficient, not augmentable
- Inputs: as S1
- Scripted: harness → `manifest-insufficient`; no more sources available
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→manifest-insufficient], land-and-verify]
- Expect gates: []
- Expect terminal: blocked

### S7 — run id missing
- Inputs: as S1
- Scripted: harness → `grounded` but `harness-run-id` absent; run-id-missing fires (abort)
- Expect visited: [scope-artifact, compile-manifest[call:compile-manifest→manifest-ready], generate-faithful[call:faithful-generation-harness→grounded], land-and-verify]  (the generate-faithful exit requires a run id, so this is reachable only if that check is skipped)
- Expect gates: []
- Expect terminal: blocked

### S8 — augmentation never succeeds
- Inputs: as S1
- Scripted: harness → `manifest-insufficient` (augmentable) on every pass
- Expect visited: [scope-artifact, (compile-manifest, generate-faithful, land-and-verify) repeated — no budget declared]
- Expect gates: []
- Expect terminal: UNSTATED

## Ambiguities for the process owner
- The augment loop (land-and-verify → compile-manifest) has no budget and "missing variables can be covered by more sources" has no state key; how new sources get into `declared-sources` on the second pass is unstated (scope-artifact is not re-run).
- The harness can halt without any terminal verdict (its false-citation and grounding-check-theatre failure modes are manual-review + blocking with no route); generate-faithful has no route for a child that stops on a person rather than returning a verdict.
- The generate-faithful exit requires a run id, so land-and-verify's `both-run-ids-present == false` branch is reachable only if compile-manifest's run id is lost; a missing harness run id at generate-faithful has no route.
- `dispatch-unresolvable` is handled by compile-manifest too, but only generate-faithful has an unresolvable route.
- Both failure modes lack `recovery_detail`; run-id-missing is `abort` while the route treats it as a named terminal.
- scope-artifact overwrites its own inputs with fixed values while `declared-sources` is "PROVIDED AT DISPATCH" — whether caller values or the step's defaults win is unstated.
- change-lifecycle calls this workflow "per work package" without passing the five plug-ins.
