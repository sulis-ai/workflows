# codebase-restructure — methodology sequence

Source: methodology/sequences/codebase-restructure/DAG.yaml, SEQUENCE.yaml, SEQUENCE.md, HANDOFF_CONTRACT.yaml
Purpose: Governed directory restructure: gather context, assess fitness, compare approaches, stress-test, verify readiness, then execute with decision and documentation tails.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-HANDOFF, UC-OUT-TYPED, UC-GATE-KINDS, UC-GATE-ROUTE, UC-GATE-VOCAB, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-PARALLEL, UC-JOIN, UC-STOP-NAMED, UC-CRITICALITY, UC-RETRY, UC-SIDE-EFFECT-CLAIM

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| outcome-project-context | outcome | Current structure, constraints, manifest | — → EXISTING_CAPABILITIES.md, CONSTRAINTS.md, PROPOSED_MANIFEST.yaml | standard |
| outcome-implementation-assessment | outcome | Fitness ratings, reuse | outcome-project-context / existing_structure → IMPLEMENTATION_ASSESSMENT.md | standard |
| outcome-options-analysis | outcome | Compare restructure approaches | outcome-implementation-assessment / assessment_results → OPTIONS_ANALYSIS.md | standard |
| gate-01 "Approach Approval" | gate (user_approval) | Person selects approach | outcome-options-analysis | critical |
| outcome-stress-testing | outcome | Adversarial validation of chosen approach | gate-01 / selected_approach, mapping_table → STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md | standard |
| outcome-execution-readiness | outcome | Verify prerequisites | outcome-stress-testing / stress_test_results → READINESS_ASSESSMENT.md | standard |
| gate-02 "Execution Approval" | gate (user_approval) | Person confirms ready to execute | outcome-execution-readiness | critical |
| outcome-codebase-restructure | outcome (side effect: moves files) | Execute restructure | gate-02 / readiness, approach, mapping, stress results → REFERENCE_ANALYSIS.md, MIGRATION_PLAN.md | critical |
| tail-decision-recording | outcome (tail) | ADR | outcome-codebase-restructure / adr_context | standard |
| tail-documentation-sync | outcome (tail) | Update docs | outcome-codebase-restructure / documentation_changes | standard |
| sequence-complete | terminal | End | tail-decision-recording, tail-documentation-sync (all_success default) | standard |

## Routes, gates, loops and contracts as declared
- DAG `type: sequence`, no `execution` block → default_join_rule all_success. Only multi-predecessor node: `sequence-complete` ← both tails → all_success join.
- Tails: both depend on outcome-codebase-restructure → parallel fan-out (HANDOFF `type: "parallel"`); SEQUENCE.yaml lists `tail_outcomes`. SEQUENCE.md: "Tail outcomes are mandatory (C-05)".
- `type: strict` (SEQUENCE.yaml/SEQUENCE.md) → no skip/reorder without approval.
- Gates (`approval_required: true`, `on_failure` UNSTATED, decision options UNSTATED):
  - gate-approach-approval: context gathered; assessment with fitness ratings; ≥2 approaches compared; selected approach justified. SEQUENCE.md adds "Constraints from implementation assessment honoured".
  - gate-execution-approval: stress test failure modes with mitigations; prerequisites verified; rollback plan documented; risk level acceptable.
- Handoffs (HANDOFF_CONTRACT.yaml; non-standard shape `handoff_contract` + top-level `transitions`):
  - project-context→implementation-assessment: EXISTING_CAPABILITIES.md, CONSTRAINTS.md; extract existing_structure; on_failure `block`, max_attempts 1.
  - implementation-assessment→options-analysis: IMPLEMENTATION_ASSESSMENT.md; extract fitness_ratings (FIT|ADAPTABLE|UNFIT); constraint IA-COMPLETE binding; `block`, 1.
  - options-analysis→stress-testing via gate-01 (`gate-controlled`): OPTIONS_ANALYSIS.md; extract selected_approach, mapping_table; APPROACH-SELECTED binding; `block`, 1.
  - stress-testing→execution-readiness: STRESS_TEST_REPORT.md; verdict PASS|CONDITIONAL|FAIL; `block`, 1.
  - execution-readiness→codebase-restructure via gate-02: READINESS_ASSESSMENT.md; readiness_status.ready bool; APPROACH-SELECTED, STRESS-TESTED, READY binding; `block`, 1.
  - codebase-restructure→[both tails] (`parallel`): REFERENCE_ANALYSIS.md, MIGRATION_PLAN.md; adr_context, documentation_changes; on_failure `warn`, 1.
- No edges, loops, routing, spirals or triads.

## Scenarios
### S1 — Happy path
- Inputs: restructure-name=src-to-monorepo
- Scripted: project-context, implementation-assessment, options-analysis → complete; gate-01 → approve; stress-testing → complete (PASS); execution-readiness → complete (ready=true); gate-02 → approve; codebase-restructure → complete; both tails → complete
- Expect visited: [outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, gate-01, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-codebase-restructure, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S2 — Gate 1 send back (reading: re-run options-analysis)
- Inputs: as S1
- Scripted: first three complete; gate-01 → send_back ("only one approach compared"); outcome-options-analysis → complete; gate-01 → approve; rest as S1
- Expect visited: [outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, gate-01, outcome-options-analysis, gate-01, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-codebase-restructure, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: send_back, gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S3 — Gate 2 reject (risk not acceptable)
- Inputs: as S1
- Scripted: to execution-readiness complete (ready=false); gate-02 → reject
- Expect visited: [outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, gate-01, outcome-stress-testing, outcome-execution-readiness, gate-02]
- Expect gates: [gate-01: approve, gate-02: reject]
- Expect terminal: rejected (no files moved)
### S4 — Handoff block: IMPLEMENTATION_ASSESSMENT.md missing (one attempt)
- Inputs: as S1
- Scripted: project-context complete; implementation-assessment → complete without artifact → validation fails, max_attempts 1 → block
- Expect visited: [outcome-project-context, outcome-implementation-assessment]
- Expect gates: []
- Expect terminal: blocked
### S5 — Handoff warn into tails: MIGRATION_PLAN.md missing
- Inputs: as S1
- Scripted: as S1 but codebase-restructure omits MIGRATION_PLAN.md → warn; tails run and complete
- Expect visited: [outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, gate-01, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-codebase-restructure, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete (1 handoff warning)
### S6 — Parallel join: one tail fails
- Inputs: as S1
- Scripted: as S1 but tail-documentation-sync → failed; tail-decision-recording → complete
- Expect visited: [outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, gate-01, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-codebase-restructure, {tail-decision-recording | tail-documentation-sync}]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: failed (sequence-complete never ready under all_success)

## Ambiguities for the process owner
- Gate decision vocabulary and `on_failure` UNSTATED for both gates; send-back targets and budgets UNSTATED (S2, S3 are readings).
- Tails depend on outcome-codebase-restructure, which runs after the last gate — contradicts the standard ("After final gate passes, tail outcomes execute"; tails share the final gate). The restructure execution itself has no gate after it.
- stress_test_results verdict FAIL and readiness ready=false have no declared route; presumably only gate-02 evidence.
- HANDOFF_CONTRACT.yaml uses a non-standard shape (`handoff_contract.sequence`, `artifact/location`, `structured_extract`, `validation.max_attempts`, `to` as a list) — not HANDOFF_CONTRACT_STANDARD v1.0.0.
- Node type `terminal` and field `outputs` are not in DAG_SCHEMA_SPECIFICATION (types step|outcome|gate).
- Tail parallelism: DAG and contract parallel; standard says tails "execute in order".
- GATE 1 criterion "Constraints from implementation assessment honoured" appears only in SEQUENCE.md.
- `max_attempts: 1` on handoff validation — whether that means no retry of the producing outcome is UNSTATED.
- Destructive step (outcome-codebase-restructure) declares no precondition or claim beyond gate-02.
