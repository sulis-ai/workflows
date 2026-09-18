# new-feature — methodology sequence

Source: methodology/sequences/new-feature/SEQUENCE.yaml (v1.0.0, status deprecated), methodology/sequences/new-feature/DAG.yaml (v4.0.0), methodology/sequences/new-feature/HANDOFF_CONTRACT.yaml (v1.0.0), methodology/sequences/new-feature/SEQUENCE.md (v5.0.0, deprecated by ADR-074 in favour of product-delivery)
Purpose: Take a feature from goal through context, assessment, options, design, planning, implementation and release, with three person gates and two parallel tail outcomes.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-HANDOFF, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-PARALLEL, UC-JOIN, UC-CALL, UC-CALL-GATES, UC-CRITICALITY, UC-STOP-NAMED, UC-VERSION

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| outcome-goal | outcome | PACER + SMART goal | — → GOAL.md, LIVING_CONTEXT.json | standard |
| outcome-project-context | outcome | Existing capabilities, constraints, tech radar | goal → EXISTING_CAPABILITIES.md, CONSTRAINTS.md | standard |
| outcome-implementation-assessment | outcome | Fitness ratings, claim verification, binding conditions IA-BC-01..07 | project-context → IMPLEMENTATION_ASSESSMENT.md | standard |
| outcome-options-analysis | outcome | Compare ≥2 approaches | implementation-assessment → OPTIONS_ANALYSIS.md, lenses/*/ANALYSIS.md | standard |
| outcome-solution-design | outcome | Working Backwards design; Design Validator before gate | options-analysis → PR_FAQ.md, USER_GUIDE.md, TEST_SCENARIOS.md, DESIGN.md, IVS.md | standard |
| outcome-stress-testing-design | outcome | Adversarial design validation, ≥2 ARC cycles | solution-design → STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md | standard |
| gate-01 | gate | Design Approval | stress-testing-design → decision | critical |
| outcome-feature-planning | outcome | Self-contained task decomposition | gate-01 → PLAN.md, TASKS.md, TASKS.yaml, tasks/*.md | standard |
| outcome-stress-testing-plan | outcome | Adversarial plan validation | feature-planning → STRESS_TEST_REPORT.md | standard |
| outcome-execution-readiness | outcome | Comprehension + prerequisites | stress-testing-plan → READINESS_ASSESSMENT.md | standard |
| gate-02 | gate | Plan Approval | execution-readiness → decision | critical |
| outcome-solution-implementation | outcome | TDD; Production Guardian before gate | gate-02 → implementation_complete | critical |
| gate-03 | gate | Release Approval | solution-implementation → decision | critical |
| outcome-feature-release | outcome | Deploy, verify; GATE 4 (user sign-off) internal | gate-03 → release_complete | critical |
| tail-decisions | outcome (tail) | ADRs | feature-release → ADR-*.md | standard |
| tail-documentation | outcome (tail) | Documentation sync | feature-release → DOCUMENTATION_PROPOSAL.md | standard |
| sequence-complete | terminal | End | both tails (default all_success) | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict` (SEQUENCE.yaml, DAG, SEQUENCE.md) → UC-EXEC-POLICY strict: "All outcomes must execute in order".
- Linear chain; no routing nodes, no edges, no loops.
- SEQUENCE.yaml `gate_after`: step 6 stress-testing → "GATE 1 — Design Approval" (user_approval); step 9 execution-readiness → "GATE 2 — Plan Approval"; step 10 solution-implementation → "GATE 3 — Release Approval". Agrees with DAG gate nodes.
- `gates.gate-design-approval`: 8 criteria, `approval_required: true`, decisions PROCEED | REVISE ("Design needs iteration") | REJECT ("Abandon feature"). SEQUENCE.md adds "If IMPLEMENTATION_ASSESSMENT.md was produced, IA binding conditions are satisfied".
- `gates.gate-plan-approval`: 6 criteria, decisions PROCEED | REVISE ("Plan needs iteration") | REJECT — SEQUENCE.md: "REJECT - Return to design" → send back to outcome-solution-design, not a terminal.
- `gates.gate-release-approval`: 5 criteria, decisions PROCEED | BLOCKED ("Implementation needs fixes") → send back to outcome-solution-implementation (best reading).
- REVISE targets, on_failure and redo budgets: UNSTATED for all gates.
- GATE 4 inside feature-release: child-process gate (UC-CALL-GATES); decisions UNSTATED here.
- Tails: `tail: true`, `parallel_with`; SEQUENCE.md `trigger: on_success, parallel: true`, "Tail outcomes are mandatory, not optional". sequence-complete joins both with default all_success.
- Available utility (SEQUENCE.md): compliant-mockup-production "may be invoked within" solution-design → optional nested call, prose only.
- Handoff contracts (`from`/`to` use outcome ids; stress-testing appears as both `to` and `from` twice):
  1. goal → project-context: GOAL.md, LIVING_CONTEXT.json → `block`.
  2. project-context → implementation-assessment: EXISTING_CAPABILITIES.md, CONSTRAINTS.md → `block`.
  3. implementation-assessment → options-analysis: IMPLEMENTATION_ASSESSMENT.md, `binding_conditions` {fitness_summary, binding_conditions} → `block`.
  4. options-analysis → solution-design: OPTIONS_ANALYSIS.md, `selected_approach`; expected input `implementation_assessment` `required: false` → `block`.
  5. solution-design → stress-testing: `design_package` (artifact_set of 5 files, exists) → `block`.
  6. stress-testing → feature-planning (via gate-01): STRESS_TEST_REPORT.md; constraint DESIGN-APPROVED binding → `block`.
  7. feature-planning → stress-testing: `plan_package` (PLAN.md, TASKS.md, tasks/ directory_exists) → `block`.
  8. stress-testing → execution-readiness: STRESS_TEST_REPORT.md (phase 08) → `block`.
  9. execution-readiness → solution-implementation (via gate-02): READINESS_ASSESSMENT.md; PLAN-APPROVED → `block`.
  10. solution-implementation → feature-release (via gate-03): `implementation_complete` {tests_passing, tasks_complete; production_guardian_verdict ∈ APPROVED|BLOCKED}; RELEASE-APPROVED → `block`.
  11. feature-release → decision-recording: `release_complete` {deployed, verified, decisions_made} → `warn`.
  12. feature-release → documentation-sync: `documentation_needs` → `warn`.
- Retry policies: UNSTATED for all transitions.

## Scenarios
### S1 — Happy path
- Inputs: feature_name="dns-management"
- Scripted: all outcomes → complete; gate-01 → approve; gate-02 → approve; gate-03 → approve (PROCEED); GATE 4 internal → approve; all contracts satisfied
- Expect visited: [outcome-goal, outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, outcome-solution-design, outcome-stress-testing-design, gate-01, outcome-feature-planning, outcome-stress-testing-plan, outcome-execution-readiness, gate-02, outcome-solution-implementation, gate-03, outcome-feature-release, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve, gate-03: approve]
- Expect terminal: complete
### S2 — Gate 1 send back once
- Scripted: gate-01 → send_back (REVISE); rerun outcome-solution-design, outcome-stress-testing-design (best reading); gate-01 → approve; rest as S1
- Expect visited: [..., outcome-stress-testing-design, gate-01, outcome-solution-design, outcome-stress-testing-design, gate-01, outcome-feature-planning, ..., sequence-complete]
- Expect gates: [gate-01: send_back, gate-01: approve, gate-02: approve, gate-03: approve]
- Expect terminal: complete
### S3 — Gate 1 reject
- Scripted: gate-01 → reject
- Expect visited: [outcome-goal, outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, outcome-solution-design, outcome-stress-testing-design, gate-01]
- Expect gates: [gate-01: reject]
- Expect terminal: rejected
### S4 — Gate 2 send back (REVISE)
- Scripted: gate-02 → send_back; rerun outcome-feature-planning, outcome-stress-testing-plan, outcome-execution-readiness (best reading); gate-02 → approve
- Expect visited: [..., gate-02, outcome-feature-planning, outcome-stress-testing-plan, outcome-execution-readiness, gate-02, outcome-solution-implementation, gate-03, outcome-feature-release, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: send_back, gate-02: approve, gate-03: approve]
- Expect terminal: complete
### S5 — Gate 2 REJECT returns to design
- Scripted: gate-02 → send_back to outcome-solution-design ("Return to design"); design, gate-01, planning chain rerun; gate-01 → approve; gate-02 → approve
- Expect visited: [..., gate-02, outcome-solution-design, outcome-stress-testing-design, gate-01, outcome-feature-planning, outcome-stress-testing-plan, outcome-execution-readiness, gate-02, outcome-solution-implementation, gate-03, outcome-feature-release, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: send_back(REJECT→design), gate-01: approve, gate-02: approve, gate-03: approve]
- Expect terminal: complete
### S6 — Gate 3 BLOCKED
- Scripted: gate-03 → send_back (BLOCKED); rerun outcome-solution-implementation; gate-03 → approve
- Expect visited: [..., outcome-solution-implementation, gate-03, outcome-solution-implementation, gate-03, outcome-feature-release, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve, gate-03: send_back, gate-03: approve]
- Expect terminal: complete
### S7 — Optional input absent (contract 4)
- Scripted: IMPLEMENTATION_ASSESSMENT.md present for contract 3 but `implementation_assessment` not mapped into solution-design; required: false
- Expect visited: as S1
- Expect gates: [gate-01: approve, gate-02: approve, gate-03: approve]
- Expect terminal: complete (optional input visibly absent)
### S8 — Handoff `block`: design package incomplete
- Scripted: outcome-solution-design → complete without IVS.md
- Expect visited: [outcome-goal, outcome-project-context, outcome-implementation-assessment, outcome-options-analysis, outcome-solution-design]
- Expect gates: []
- Expect terminal: blocked ("Feature design must be complete before stress-testing")
### S9 — Handoff `block`: plan tasks directory missing
- Scripted: gate-01 → approve; outcome-feature-planning → complete without tasks/
- Expect visited: [..., gate-01, outcome-feature-planning]
- Expect gates: [gate-01: approve]
- Expect terminal: blocked
### S10 — Handoff `warn`: release summary missing decisions
- Scripted: S1; feature-release → `release_complete` without `decisions_made`; `documentation_needs` absent
- Expect visited: as S1
- Expect gates: [gate-01: approve, gate-02: approve, gate-03: approve]
- Expect terminal: complete (two warnings)
### S11 — Tail failure blocks completion
- Scripted: S1; tail-decisions → failed
- Expect visited: [..., outcome-feature-release, {tail-decisions | tail-documentation}]
- Expect terminal: blocked (sequence-complete not ready under all_success)

## Ambiguities for the process owner
- Whole sequence is deprecated (SEQUENCE.yaml `status: deprecated`, ADR-074) but still has an executable DAG; whether an engine should refuse, warn or run it is UNSTATED.
- SEQUENCE.yaml uses bare outcome ids (step 6 and 8 both `stress-testing`); DAG uses `outcome-stress-testing-design` / `-plan`; contracts use bare `stress-testing` for four transitions, so contracts 6 and 8 cannot be keyed unambiguously by `from`.
- SEQUENCE.yaml lists tail_outcomes as a flat list; DAG/SEQUENCE.md say parallel on_success. Node type `terminal`, fields `tail`, `parallel_with`, `outputs`, `agent_instructions` not in DAG schema.
- Gate REVISE targets and redo budgets UNSTATED; GATE 2 "REJECT - Return to design" turns a reject into a send-back; GATE 3 uses BLOCKED instead of REVISE/REJECT — three vocabularies in one sequence.
- GATE 1 SEQUENCE.md criteria include an "if produced" condition on IMPLEMENTATION_ASSESSMENT.md, although the DAG makes implementation-assessment a mandatory step and contract 3 blocks without it.
- GATE 4 is "internal" to feature-release; how it surfaces is UNSTATED.
- outcome-goal instructions say "Auto-proceed to options-analysis", but its successor is project-context (stale text).
- DAG header comment "Version: 3.0.0" vs `version: "4.0.0"`; SEQUENCE.md 5.0.0; SEQUENCE.yaml 1.0.0.
- `artifact_set` output type and `directory_exists` validation are not in HANDOFF_CONTRACT_STANDARD (which allows artifact | structured, exists | schema).
- Contract 10 permits `production_guardian_verdict: BLOCKED` while gate-03 requires Guardian approval; no route for a BLOCKED verdict before the gate.
- compliant-mockup-production optional invocation is prose only.
- Terminal verdict names other than completion UNSTATED; retry policies UNSTATED.
