# architecture-evolution — methodology sequence

Source: methodology/sequences/architecture-evolution/SEQUENCE.yaml, SEQUENCE.md, HANDOFF_CONTRACT.yaml, ROUTING_GUIDE.md (no DAG.yaml)
Purpose: Evolve an internal platform primitive (port, adapter, model, contract) through goal, context, diagnosis/spec/plan and stress test, then a manual migration and two approval gates.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-HANDOFF, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-PARALLEL, UC-JOIN, UC-STOP-NAMED, UC-MECHANISM, UC-OUT-TYPED, UC-SEED-ARTIFACTS

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| goal | outcome | Well-formed goal for the evolution | — → GOAL.md, LIVING_CONTEXT.json | UNSTATED |
| project-context | outcome | Capabilities, constraints, radar focused on the target primitive | goal / GOAL.md → EXISTING_CAPABILITIES.md, CONSTRAINTS.md, consumer_dependencies (derived) | UNSTATED |
| architecture-evolution | outcome | Diagnose, specify target, plan A→B→M→D migration | project-context → DIAGNOSIS.md, ARCHITECTURE_SPEC.md, MIGRATION_PLAN.md, evolution_summary | UNSTATED |
| stress-testing | outcome | Adversarial validation of spec + plan | architecture-evolution → STRESS_TEST_REPORT.md, stress_test_results | UNSTATED |
| gate-1 "Architecture Spec + Migration Plan Approval" | gate (user_approval) | Person approves spec + plan | stress-testing | UNSTATED |
| implementation | step (manual, person) | Execute MIGRATION_PLAN.md phase by phase | gate-1 / spec, plan, report → migration_execution_log, migration_results | UNSTATED |
| gate-2 "Migration Complete" | gate (user_approval) | Person confirms migration verified | implementation / log, results | UNSTATED |
| decision-recording | outcome (tail) | ADR for decisions | gate-2 / decisions_made, ARCHITECTURE_SPEC.md | UNSTATED |
| documentation-sync | outcome (tail) | Update affected docs | gate-2 / ARCHITECTURE_SPEC.md, MIGRATION_PLAN.md | UNSTATED |

## Routes, gates, loops and contracts as declared
- Order: linear steps 1→4 (SEQUENCE.yaml `steps`) → strictly sequential (UC-SEQUENCE). `type: strict` → deviation requires explicit approval (UC-EXEC-POLICY).
- No DAG.yaml, no join rules, no edges, no loops, no routing nodes.
- gate_after step 4: `GATE 1`, `type: user_approval` → approval gate. Criteria (SEQUENCE.md): DIAGNOSIS consumer map with file counts; spec with port/adapter interfaces; consistency check passes; plan has Phase Applicability; per-phase verification criteria; stress-test mitigates failure modes; "All triad lenses signed off". Decisions: PROCEED → implementation; REVISE → "Spec or plan needs iteration" (re-entry target UNSTATED; Type B orchestrator-managed); REJECT → "Abandon evolution" (terminal).
- GATE 2 exists only in SEQUENCE.md prose and a SEQUENCE.yaml comment: `type: user_approval`, criteria: applicable phases verified; partial completion has deferral justification + follow-up; tests passing; no stale references (or deferred); grep verification. Decisions: PROCEED → tail outcomes; BLOCKED → "Migration needs fixes" (return target UNSTATED; reading: back to implementation).
- Step 5 implementation: manual person step; "The SequenceExecutionEngine pauses after GATE 1 and waits for the user to complete implementation + submit GATE 2" → input-style human step (UC-GATE-KINDS input) followed by approval.
- Tail outcomes: `decision-recording`, `documentation-sync`; SEQUENCE.md `trigger: on_success`, `parallel: true`; "mandatory, not optional" → parallel fan-out after gate-2 PROCEED, no join after (process ends when both finish; join rule UNSTATED, reading all_success).
- Handoff contracts (all `required_outputs` validation `exists` unless structured):
  - goal→project-context: GOAL.md, LIVING_CONTEXT.json; on_failure `block`.
  - project-context→architecture-evolution: EXISTING_CAPABILITIES.md, CONSTRAINTS.md; derived input consumer_dependencies (schema primitive_name, consumers[]); on_failure `block`.
  - architecture-evolution→stress-testing: DIAGNOSIS.md, ARCHITECTURE_SPEC.md, MIGRATION_PLAN.md, evolution_summary (enum evolution_type, applicable_phases); on_failure `block`.
  - stress-testing→implementation: STRESS_TEST_REPORT.md, stress_test_results (verdict PASS|CONDITIONAL|FAIL); constraints_passed ARCH-SPEC-APPROVED, STRESS-TESTED (binding); on_failure `block`.
  - implementation→gate-2: migration_execution_log, migration_results (phases_executed, tests_passing); on_failure `block`.
  - gate-2→decision-recording: migration_complete; on_failure `warn`.
  - gate-2→documentation-sync: documentation_needs; on_failure `warn`.
- No verification spiral, no retry_policy, no lens triads declared at sequence level (gate criterion references triad sign-off inside outcomes).
- Routing discriminator ("Does the HTTP API change?") selects this sequence before it starts; not an in-process route.

## Scenarios
### S1 — Happy path, both gates proceed
- Inputs: evolution-name=document-repository-split, brief="split DocumentRepository into read/write ports"
- Scripted: goal → complete, project-context → complete, architecture-evolution → complete (evolution_type=decomposition), stress-testing → complete (verdict PASS); gate-1 → approve; implementation → input submitted (log + results tests_passing=true); gate-2 → approve; decision-recording → complete; documentation-sync → complete
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1, implementation, gate-2, {decision-recording | documentation-sync}]
- Expect gates: [gate-1: approve, gate-2: approve]
- Expect terminal: complete
### S2 — GATE 1 send back (REVISE)
- Inputs: as S1
- Scripted: as S1 to stress-testing; gate-1 → send_back (note "plan lacks bridge verification"); architecture-evolution → complete; stress-testing → complete; gate-1 → approve; rest as S1
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1, architecture-evolution, stress-testing, gate-1, implementation, gate-2, {decision-recording | documentation-sync}]
- Expect gates: [gate-1: send_back, gate-1: approve, gate-2: approve]
- Expect terminal: complete
### S3 — GATE 1 reject
- Inputs: as S1
- Scripted: first four outcomes complete; gate-1 → reject
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1]
- Expect gates: [gate-1: reject]
- Expect terminal: rejected (abandoned)
### S4 — GATE 2 blocked, fixes, then proceed
- Inputs: as S1
- Scripted: as S1 to gate-2; gate-2 → send_back ("BLOCKED: stale references remain"); implementation → input submitted; gate-2 → approve; tails complete
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1, implementation, gate-2, implementation, gate-2, {decision-recording | documentation-sync}]
- Expect gates: [gate-1: approve, gate-2: send_back, gate-2: approve]
- Expect terminal: complete
### S5 — Handoff block: architecture-evolution misses MIGRATION_PLAN.md
- Inputs: as S1
- Scripted: goal, project-context complete; architecture-evolution → complete but MIGRATION_PLAN.md missing → contract on_failure block
- Expect visited: [goal, project-context, architecture-evolution]
- Expect gates: []
- Expect terminal: blocked ("Architecture evolution artifacts must be complete before stress-testing can begin")
### S6 — Handoff block before gate-2: no migration_results
- Inputs: as S1
- Scripted: as S1 to implementation; implementation → submitted with log only → block
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1, implementation]
- Expect gates: [gate-1: approve]
- Expect terminal: blocked ("Migration execution evidence must be provided for GATE 2 review")
### S7 — Handoff warn to tails: decisions_made absent
- Inputs: as S1
- Scripted: as S1, but gate-2 output lacks migration_complete/documentation_needs → warn on both tail transitions; tails still run and complete
- Expect visited: [goal, project-context, architecture-evolution, stress-testing, gate-1, implementation, gate-2, {decision-recording | documentation-sync}]
- Expect gates: [gate-1: approve, gate-2: approve]
- Expect terminal: complete (with 2 handoff warnings recorded)

## Ambiguities for the process owner
- GATE 2 and the implementation step exist only in SEQUENCE.md prose and a SEQUENCE.yaml comment; SEQUENCE.yaml declares neither, so an engine reading SEQUENCE.yaml alone would run tails straight after GATE 1.
- SEQUENCE.yaml `tail_outcomes` is a plain list (standard says tails run "in order"); SEQUENCE.md says `parallel: true`. Parallel vs ordered is undecided.
- GATE 1 REVISE and GATE 2 BLOCKED re-entry targets are UNSTATED (read as architecture-evolution and implementation respectively); redo budgets UNSTATED.
- Gate vocabulary is PROCEED/REVISE/REJECT for GATE 1 but PROCEED/BLOCKED for GATE 2 (no reject on GATE 2).
- Gate criterion "All triad lenses signed off" refers to triads not declared anywhere in this sequence.
- stress_test_results verdict FAIL/CONDITIONAL has no declared route; reading: surfaced to GATE 1 only.
- "Tail outcomes are mandatory, not optional" contradicts the general standard ("Tail outcomes are skipped if explicitly not needed").
- Contracts name nodes `implementation` and `gate-2` that no structural file declares.
- ROUTING_GUIDE: "if the evolution reveals that HTTP API changes are needed, the gate review can redirect to new-feature" — a send-elsewhere decision (UC-GATE-HANDOFF) with no declared route.
- Utilities (options-analysis, codebase-restructure, execution-readiness) "may be invoked within specific steps" — optional calls with no declared condition.
- Criticality, retry policy, timeouts all UNSTATED.
