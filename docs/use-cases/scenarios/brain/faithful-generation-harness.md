# faithful-generation-harness — brain

Source: plugins/sulis-brain/instances/faithful-generation-harness/workflow.jsonld
Purpose: Generate provenance-grounded content from a closed context manifest by committing a claim→variable binding table, expanding only committed bindings, and grounding-checking every span.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-STOP-HONEST, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-COMPENSATE, UC-CALL, UC-FAILURE-MODES, UC-REFUSAL-MODE, UC-CRITICALITY, UC-MECHANISM, UC-TOOL-KINDS, UC-TRIGGER, UC-FIDELITY, UC-SPIRAL

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| observe-manifest | mixed | Validate structure + closure of `context-manifest` (not goal-sufficiency) | — |
| orient-select-relevant | mixed | Select manifest variables relevant to the goal → `relevant-subset` | — |
| decide-commit-bindings | probabilistic | Commit claim→variable_id bindings; record gaps with load_bearing → `binding-table` (also `load-bearing-claims`, `goal-reducible` per postconditions) | — |
| act-generate-from-bindings | probabilistic | Expand only bindings; flag glue text → `generated-content`, `span-citations`, `unattributed-spans` | dispatch-judged-claim (workflow_dispatch → `ooda-spiral` dna:workflow:01KT3SPRXWFNN5VJBSKNX8YGKS; alternate `critical-thinking` dna:workflow:01KT1N632VCT1J0XWY7NMVDHCJ) — OPTIONAL, per judged claim |
| self-critique-grounding | mixed | Per-span grounding check, binding validity, false-citation detection, verdict → `grounding-report`, `binding-validity`, `false-citation-detected`, `final-verdict`, `residual-unattributed` | — |

## Routes as declared
- `observe-manifest -> orient-select-relevant [if context-manifest is STRUCTURALLY well-formed (non-empty; every entry has variable_id+meaning+value; variable_ids unique; manifest closed …) — NOTE: structural well-formedness is NOT goal-sufficiency …]` → condition: structural validity (derivable deterministically; no state key holds it).
- `observe-manifest -> [terminal:manifest-insufficient] [if STRUCTURAL insufficiency ONLY and unrepairable: … AND no recoverable subset exists — manifest-not-closed FailureMode escalates. …]` → terminal `manifest-insufficient`.
- `orient-select-relevant -> decide-commit-bindings` → unconditional.
- `decide-commit-bindings -> act-generate-from-bindings [if every LOAD-BEARING claim … is bound to a manifest variable_id, AND any remaining gaps are REDUCIBLE … — REDUCE+proceed]` → condition `goal-reducible == true`.
- `decide-commit-bindings -> [terminal:manifest-insufficient] [if GOAL-RELATIVE insufficiency: an unbindable claim is LOAD-BEARING … AND the goal is NOT reducible to exclude it — binding-table-incomplete-or-invalid FailureMode escalates. …]` → condition `goal-reducible == false` → terminal `manifest-insufficient`.
- `act-generate-from-bindings -> self-critique-grounding` → unconditional.
- `self-critique-grounding -> act-generate-from-bindings [if an ungrounded span is detected whose binding EXISTS — CYCLE: regenerate the span from its binding; increment revision-count]` → loop; counter `revision-count`; budget UNSTATED; condition from `grounding-report` (ungrounded span with binding).
- `self-critique-grounding -> decide-commit-bindings [if a needed claim has no binding — CYCLE BACK: the binding table is incomplete, re-decide before re-generating]` → loop; condition from `grounding-report` / `binding-validity == false`; budget UNSTATED.
- `self-critique-grounding -> [terminal:grounded] [if every span is EITHER bound + grounded OR a STRUCTURAL inference …, AND there is NO unbindable-claim span, AND no false-citation-detected, AND binding-validity == true — DR-037 …]` → terminal `grounded`.
- `self-critique-grounding -> [terminal:partial-unattributed] [if at least one span is an UNBINDABLE-CLAIM …, explicitly flagged unattributed (NOT falsely cited) AND no false-citation-detected — honest partial provenance; …]` → terminal `partial-unattributed`.

## Scenarios
### S1 — grounded
- Inputs: `context-manifest: [{variable_id: op-surface, meaning: "operations", value: "open/send/read/health/status/close"}, …]`, `generation-goal: "describe the consumer operations"`
- Scripted: observe → well-formed; orient → 5 variables; decide → all claims bound, `goal-reducible: true`; act → content with citations; self-critique → all supported, `binding-validity: true`, `false-citation-detected: false`
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding]
- Expect gates: []
- Expect terminal: grounded

### S2 — structurally broken manifest
- Inputs: `context-manifest: []`
- Scripted: observe → empty, unrepairable; manifest-not-closed fires
- Expect visited: [observe-manifest]
- Expect gates: []
- Expect terminal: manifest-insufficient

### S3 — well-formed but under-provisioned for the goal
- Inputs: manifest without `incurred_losses`/`earned_premium`, `generation-goal: "report the loss ratio"`
- Scripted: decide → load-bearing gap, `goal-reducible: false`; binding-table-incomplete-or-invalid fires
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings]
- Expect gates: []
- Expect terminal: manifest-insufficient

### S4 — reducible gap, honest partial provenance
- Inputs: as S1, goal "may include" an unsupported example
- Scripted: decide → non-load-bearing gap, `goal-reducible: true`; self-critique → one unbindable-claim span flagged unattributed, no false citation
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding]
- Expect gates: []
- Expect terminal: partial-unattributed

### S5 — ungrounded span regenerated once
- Inputs: as S1
- Scripted: self-critique pass 1 → one span drifted, binding exists, `revision-count` 0→1; act regenerates; pass 2 → all grounded
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding, act-generate-from-bindings, self-critique-grounding]
- Expect gates: []
- Expect terminal: grounded

### S6 — missing binding, re-decide once
- Inputs: as S1
- Scripted: self-critique pass 1 → a needed claim has no binding; decide adds binding; act; pass 2 → grounded
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding]
- Expect gates: []
- Expect terminal: grounded

### S7 — regeneration never grounds
- Inputs: as S1
- Scripted: self-critique → same span ungrounded every pass
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, (act-generate-from-bindings, self-critique-grounding) repeated — no budget]
- Expect gates: []
- Expect terminal: UNSTATED

### S8 — judged claim pressure-tested before expansion
- Inputs: as S1, goal includes a recommendation
- Scripted: act dispatches ooda-spiral for the recommendation → `converged`; expansion proceeds; self-critique → grounded
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings[call:ooda-spiral→converged], self-critique-grounding]
- Expect gates: []
- Expect terminal: grounded

### S9 — false citation detected
- Inputs: as S1
- Scripted: self-critique → a span cites a variable that does not support it, `false-citation-detected: true`; false-citation fires (manual-review, blocks)
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding]
- Expect gates: [manual review of the offending span (surfaced to operator or parent)]
- Expect terminal: none — halted awaiting review (no route declared)

### S10 — grounding-check theatre detected
- Inputs: as S1
- Scripted: self-critique → templated identical rationales for every span; grounding-check-theatre fires (manual-review, blocks)
- Expect visited: [observe-manifest, orient-select-relevant, decide-commit-bindings, act-generate-from-bindings, self-critique-grounding]
- Expect gates: [manual review]
- Expect terminal: none — halted awaiting review (no route declared)

## Ambiguities for the process owner
- Neither self-critique cycle has a budget; `revision-count` is counted but never compared to a limit.
- The false-citation and grounding-check-theatre failure modes block with manual-review but have no route or terminal; what a reviewer's decision does (regenerate, abort, accept) is unstated, and with `false-citation-detected == true` no terminal route matches.
- The regenerate-vs-re-decide routes are not mutually exclusive (a report can contain both an ungrounded span and a missing binding); precedence is unstated.
- The act step's in-step route "STOP … route back to decide-commit-bindings" is not a declared transition from act.
- The optional judged-claim dispatch has two alternate targets (ooda-spiral or critical-thinking) chosen by judgement, per claim (a for-each), and how a non-converged child verdict affects expansion is unstated.
- `load-bearing-claims` and `goal-reducible` are required state keys but decide-commit-bindings lists only `binding-table` as output; `goal-reducible` is what the routes read.
- The observe-manifest condition ("structurally well-formed", "no recoverable subset") has no state key; "repair and proceed" for mis-shaped fields rewrites `context-manifest` in place.
- `terminal_steps` lists only self-critique-grounding while observe and decide can also terminate.
