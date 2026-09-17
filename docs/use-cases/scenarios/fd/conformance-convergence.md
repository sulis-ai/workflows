# Conformance convergence — fd

Source: fd-product-architecture/processes/conformance-convergence.process.yaml
Purpose: Move one contract from its current shape to its target profile — build it, evolve it in place, or run a Strangler Fig expand/migrate/contract loop until the measured delta is zero.
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-DECIDE, UC-PATHS, UC-ROUTE-DEFAULT, UC-PRECONDITION, UC-TERMINATES-WHEN, UC-LOOP-BUDGET, UC-FOREACH, UC-OUT-MULTI, UC-STATE-CHANNELS, UC-STOP-NAMED, UC-CALL, UC-TOOL-KINDS

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | entry_decision | decide (tool `classify-convergence-path`) | Does a current implementation exist; is the delta additive or breaking? | `contract_ref`, `target_form`, `current_implementation_exists` → `convergence_path` |
| greenfield | build-to-target | tool (`build-to-target-grounded`) | One work package implementing the contract to its full target profile. | `contract_ref`, `target_form`, `governed_sources` → `work_package` |
| brownfield-compatible | evolve-in-place | tool (`evolve-in-place`), precondition | One work package adding the additive delta in place. | `contract_ref`, `target_form`, `governed_sources` → `work_package` |
| brownfield-breaking | expand | tool (`expand-parallel-change`), precondition | Stand the new version up alongside the old. | `contract_ref`, `target_form`, `governed_sources` → `work_package` |
| brownfield-breaking | test | tool (`test-equivalence`) | Prove both versions conform and are equivalent on overlap. | same → `equivalence` |
| brownfield-breaking | enumerate-consumers | tool (`enumerate-consumers`) | List every consumer of the current version from the topology. | `contract_ref` → `consumer_list` |
| brownfield-breaking | migrate | tool (`migrate-consumers`), precondition | One work package per consumer switching it to the new version. | `contract_ref`, `target_form`, `governed_sources`, `consumer_list` → `work_package` (×consumers) |
| brownfield-breaking | publish | tool (`publish-deprecation`) | Mark old version deprecated with successor and sunset; notify consumers. | `contract_ref`, `replaced_by`, `deprecation_date`, `sunset_date` → `deprecation_signal` |
| brownfield-breaking | drained-removal | tool (`drain-and-remove`), `destructive: true`, precondition | Remove the old version only after a re-measured zero-consumer proof. | `contract_ref`, `target_form`, `governed_sources`, `consumer_list` → `work_package` |
| brownfield-breaking | re-measure | tool (`re-measure-delta`) | Re-extract and recompute current-vs-target delta. | `contract_ref`, `target_form`, `governed_sources` → `delta` |

## Routes as declared
- Entry decision: bound to Tool `classify-convergence-path`; its answer (`convergence_path`, or `.path`) must name a branch path. Branches: no implementation → `greenfield`; exists + additive → `brownfield-compatible`; exists + breaking → `brownfield-breaking`. An unrecognised answer raises (no default): declared only in executor, `executor/service_layer/compile_generic.py:192-210`.
- greenfield: `start: build-to-target` → `next: [end]`. `on_fail` (prose): "iterate until conformance passes" — no edge, no budget (UNSTATED).
- brownfield-compatible: `start: evolve-in-place` → `next: [end]`. `precondition`: delta provably additive. `on_fail` (prose): re-enter entry decision as breaking — no `on_fail_goto` (UNSTATED as structure).
- brownfield-breaking (`recursive: true`): `start: expand` → test → enumerate-consumers → migrate → publish → drained-removal → re-measure → `end`.
  - `terminates_when`: re-measure reports `delta == 0` and no consumer remains on the old version. Per spec §7, on reaching `end` with the predicate false, re-enter at `start` (`expand`). Budget: UNSTATED in definition; spec §7 requires a depth bound; declared only in executor as the graph backstop `RECURSION_LIMIT = 60` supersteps (`executor/domain/guards.py:17`) — and the executor never evaluates `terminates_when` for this path (`compile_generic.py` wires `next` only).
  - `re-measure.on_fail` (prose): "delta != 0 → re-enter the entry decision for the residual delta" — conflicts with spec §7's "re-enter at start".
  - `test.on_fail` (prose): do not proceed to migrate. `migrate.on_fail`: roll back that consumer and retry; others unaffected. `publish.on_fail`: do not proceed to removal. `drained-removal.on_fail`: blocked, return to `migrate` until consumer count is zero. None has `on_fail_goto`; per spec §6 each halts.
  - `drained-removal` precondition MUST be evaluated before the destructive step (spec §6); the executor does not evaluate preconditions.
- No approval gates, no `methodology_ref` calls out. This process is the callee of grounded-inquiry `decompose-to-work`.
- Terminal verdict names: UNSTATED; below `end`, `halted:<step>`, `refused:entry`.

## Scenarios
### S1 — Greenfield contract
- Inputs: `contract_ref` = `survey/survey-api/create-survey`; `target_form` = `rest_endpoint`; `current_implementation_exists` = `"false"`
- Scripted: entry → `greenfield`; build-to-target → 1 work_package
- Expect visited: [entry_decision, build-to-target]
- Expect gates: []
- Expect terminal: end

### S2 — Additive delta evolved in place
- Inputs: `contract_ref` = `survey/survey-api/get-survey`; `target_form` = `rest_endpoint`; `current_implementation_exists` = `"true"`
- Scripted: entry → `brownfield-compatible`; precondition additive holds; evolve-in-place → 1 work_package, all consumers pass
- Expect visited: [entry_decision, evolve-in-place]
- Expect gates: []
- Expect terminal: end

### S3 — "Additive" delta breaks a consumer
- Inputs: as S2
- Scripted: entry → `brownfield-compatible`; evolve-in-place verification → a consumer regresses
- Expect visited: [entry_decision, evolve-in-place, entry_decision, expand, test, enumerate-consumers, migrate, publish, drained-removal, re-measure]
- Expect gates: []
- Expect terminal: end (best reading of on_fail prose: re-enter entry, reclassified breaking); executor today: end after evolve-in-place

### S4 — Breaking change converges in one pass
- Inputs: `contract_ref` = `survey/events/survey-created`; `target_form` = `event`; `current_implementation_exists` = `"true"`; host supplies `replaced_by`, `deprecation_date`, `sunset_date`
- Scripted: entry → `brownfield-breaking`; test → equivalent; enumerate → [consumer-a, consumer-b]; migrate → 2 work_packages; publish → signal emitted; drained-removal precondition → zero consumers; re-measure → delta 0
- Expect visited: [entry_decision, expand, test, enumerate-consumers, migrate, publish, drained-removal, re-measure]
- Expect gates: []
- Expect terminal: end (terminates_when holds)

### S5 — Breaking change needs a second pass
- Inputs: as S4
- Scripted: pass 1 as S4 except re-measure → delta 1 (one field still off target); pass 2 all steps succeed, re-measure → delta 0
- Expect visited: [entry_decision, expand, test, enumerate-consumers, migrate, publish, drained-removal, re-measure, expand, test, enumerate-consumers, migrate, publish, drained-removal, re-measure]
- Expect gates: []
- Expect terminal: end (per spec §7 re-enter at `start`; re-measure prose says re-enter the entry decision instead — see ambiguities; executor today ends after pass 1)

### S6 — Delta never reaches zero
- Inputs: as S4
- Scripted: re-measure → delta 1 on every pass
- Expect visited: [entry_decision, (expand … re-measure) × N]
- Expect gates: []
- Expect terminal: UNSTATED bound — spec §7 demands a deterministic stop at a depth bound; no value declared (executor backstop only: RECURSION_LIMIT 60 raises)

### S7 — Equivalence not proven
- Inputs: as S4
- Scripted: expand → ok; test → equivalence assertion fails
- Expect visited: [entry_decision, expand, test]
- Expect gates: []
- Expect terminal: halted:test

### S8 — Drain precondition fails before removal
- Inputs: as S4
- Scripted: …publish → ok; drained-removal precondition → 1 consumer still on old version
- Expect visited: [entry_decision, expand, test, enumerate-consumers, migrate, publish]
- Expect gates: []
- Expect terminal: halted:drained-removal (step not run; prose says return to migrate — no edge, no budget)

### S9 — Deprecation signal cannot be emitted
- Inputs: as S4
- Scripted: publish → notification fails
- Expect visited: [entry_decision, expand, test, enumerate-consumers, migrate, publish]
- Expect gates: []
- Expect terminal: halted:publish

### S10 — Classifier names no path
- Inputs: as S1
- Scripted: entry → `convergence_path = "unknown"`
- Expect visited: [entry_decision]
- Expect gates: []
- Expect terminal: refused:entry (declared only in executor, raises)

## Ambiguities for the process owner
- `brownfield-breaking` has two different re-entry targets: spec §7 (re-enter at `start` = `expand`) versus `re-measure.on_fail` prose (re-enter the entry decision). S5 differs by whether `entry_decision` repeats.
- No loop budget or depth bound is declared for the breaking path; spec §7 requires one. The executor never evaluates `terminates_when` here and only has the graph backstop `RECURSION_LIMIT = 60` (`executor/domain/guards.py:17`).
- Every failure route on the breaking path (`test`, `migrate`, `publish`, `drained-removal`) and the greenfield "iterate" is prose only; `drained-removal`'s "return to migrate" and `migrate`'s per-consumer retry have no edge and no budget.
- `drained-removal` is destructive and carries a precondition, but the reference executor evaluates no preconditions (spec §6 MUST).
- `evolve-in-place` failure "re-enter the entry decision as breaking" presumes the classifier will answer differently the second time; nothing forces the path.
- `migrate` produces one work package per consumer (for-each semantics) with no declared concurrency or isolation.
- `governed_sources`, `replaced_by`, `deprecation_date`, `sunset_date` are read but not declared inputs (host-provided, UC-IN-AMBIENT).
- An unrecognised classifier answer raising is declared only in executor (`compile_generic.py:192-210`).
- As the callee of grounded-inquiry `decompose-to-work`, its required inputs `contract_ref`/`target_form` have no declared mapping from a recommendation.
