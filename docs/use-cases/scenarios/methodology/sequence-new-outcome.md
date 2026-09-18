# new-outcome — methodology sequence

Source: methodology/sequences/new-outcome/DAG.yaml (v1.0.0), methodology/sequences/new-outcome/SEQUENCE.md (v1.0.0), methodology/sequences/new-outcome/HANDOFF_PROTOCOL.md (v1.0.0)
Purpose: Introduce a new OFM outcome through research, options, stress testing, creation and independent fresh-session validation, with four person gates, a bounded refinement loop and two parallel tail outcomes.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-VERDICT-ROUTE, UC-LOOP-BUDGET, UC-COMPENSATE, UC-HANDOFF, UC-OUT-MULTI, UC-PRECONDITION, UC-PARALLEL, UC-JOIN, UC-CRITICALITY, UC-STOP-NAMED, UC-RESUME

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| outcome-research | outcome | Evidence on need, patterns, prior art | — → RESEARCH_SYNTHESIS.md, lenses/*/ANALYSIS.md | standard |
| gate-research | gate | GATE 1 Research Complete | outcome-research → decision | critical |
| outcome-options | outcome | Compare design options (triad, structure, templates) | gate-research → OPTIONS_ANALYSIS.md, lenses/*/ANALYSIS.md | standard |
| gate-design | gate | GATE 2 Design Selected | outcome-options → decision | critical |
| outcome-stress | outcome | Adversarial test of chosen design | gate-design → STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md, lenses/*/ANALYSIS.md | standard |
| gate-stress | gate | GATE 3 Design Validated | outcome-stress → decision | critical |
| outcome-creation | outcome | Create outcome bundle | gate-stress (and loop from outcome-validation) → OUTCOME.md, lenses/*.md, templates/*.md, pulse/, HANDOFF.md | critical |
| context-separation | step (`checkpoint`, manual) | Pause; user starts a new agent session | outcome-creation → session change | critical |
| outcome-validation | outcome | Independent validation in fresh context | context-separation → reviews/validation-{date}.md, `validation_decision` | critical |
| gate-validation | gate | GATE 4 Outcome Validated | outcome-validation → decision | critical |
| tail-decisions | outcome (tail) | ADRs | gate-validation → ADR-*.md | standard |
| tail-documentation | outcome (tail) | Documentation sync (register in index.md) | gate-validation → DOCUMENTATION_PROPOSAL.md | standard |
| sequence-complete | terminal | End | both tails (default all_success) | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict` (SEQUENCE.md; DAG metadata has no `sequence_type`). Linear chain plus one loop.
- Loop on outcome-validation: `loop: {condition: "validation_decision == BLOCKED", target: "outcome-creation", max_iterations: 3}` → bounded back-edge validation → creation. Exhaustion behaviour UNSTATED; prose: "Repeat until VALIDATED or decision to ABANDON".
- Refinement (SEQUENCE.md prose): BLOCKED findings become input to creation triad; each re-submission goes to validation "in NEW session" → loop passes context-separation again.
- `gates.gate-1-research-complete`: 4 criteria; decisions PROCEED | REVISE ("Need unclear, iterate research") | REJECT ("Need not validated, abandon sequence").
- `gates.gate-2-design-selected`: 5 criteria; PROCEED | REVISE ("Need more options or analysis") | REJECT ("No acceptable design, abandon sequence").
- `gates.gate-3-design-validated`: 5 criteria; PROCEED | REVISE ("Address critical risks, iterate design") | REJECT ("Unacceptable risk level, abandon sequence").
- `gates.gate-4-outcome-validated`: 4 criteria (VALIDATED or VALIDATED WITH WARNINGS; "Outcome NOT registered until this gate passes"); decisions PROCEED | BLOCKED (`# Returns to outcome-creation for refinement`) → send back to outcome-creation.
- All gates `approval_required: true`; on_failure UNSTATED; REVISE targets UNSTATED (best reading: rerun the outcome immediately before the gate); gate send-back budgets UNSTATED.
- `context-separation-requirement` (`type: enforcement_checkpoint`): mechanism manual, instruction "User must start new agent session", verification "Session ID different from outcome-creation session" → precondition on outcome-validation; failure behaviour UNSTATED.
- Tails: `tail: true`, `parallel_with`, depend on gate-validation; SEQUENCE.md `trigger: on_success, parallel: true`, mandatory.
- HANDOFF_PROTOCOL.md (not a HANDOFF_CONTRACT.yaml; no on_failure policy anywhere):
  1. research-synthesis → options-analysis: RESEARCH_SYNTHESIS.md + three lens analyses; context keys necessity_validated, gap_analysis, …; validation "Necessity is validated (not rejected)".
  2. options-analysis → stress-testing: OPTIONS_ANALYSIS.md + three lens analyses; selected_option, triad_design, …
  3. stress-testing → outcome-creation: STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md + three lens analyses; "No unmitigated CRITICAL failure modes".
  4. outcome-creation → outcome-validation: OUTCOME.md, lenses, templates, pulse/OUTCOME.md, HANDOFF.md; "Exactly 3 lens files exist", "Entry NOT yet in index.md"; `context_separation.required: true`.
  5. outcome-validation → tail_outcomes: validation report; "Validation decision is not BLOCKED".
  R. outcome-validation → outcome-creation (refinement): validation report; context keys blocking_findings, remediation_guidance, iteration_count; "At least one BLOCKING finding present".

## Scenarios
### S1 — Happy path
- Inputs: outcome_name="risk-assessment", category="utility"
- Scripted: all outcomes → complete; gates 1-3 → approve; context-separation → new session confirmed; outcome-validation → VALIDATED; gate-validation → approve (PROCEED)
- Expect visited: [outcome-research, gate-research, outcome-options, gate-design, outcome-stress, gate-stress, outcome-creation, context-separation, outcome-validation, gate-validation, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: approve, context-separation: approve, gate-validation: approve]
- Expect terminal: complete
### S2 — Gate 1 send back once
- Scripted: gate-research → send_back (REVISE); outcome-research reruns; gate-research → approve; rest as S1
- Expect visited: [outcome-research, gate-research, outcome-research, gate-research, outcome-options, ..., sequence-complete]
- Expect gates: [gate-research: send_back, gate-research: approve, gate-design: approve, gate-stress: approve, context-separation: approve, gate-validation: approve]
- Expect terminal: complete
### S3 — Gate 1 reject
- Scripted: gate-research → reject
- Expect visited: [outcome-research, gate-research]
- Expect gates: [gate-research: reject]
- Expect terminal: rejected (abandoned)
### S4 — Gate 2 send back, then reject at gate 2
- Scripted: gate-design → send_back; outcome-options reruns; gate-design → reject
- Expect visited: [outcome-research, gate-research, outcome-options, gate-design, outcome-options, gate-design]
- Expect gates: [gate-research: approve, gate-design: send_back, gate-design: reject]
- Expect terminal: rejected
### S5 — Gate 3 send back once
- Scripted: gate-stress → send_back ("iterate design"); best reading: rerun outcome-stress; gate-stress → approve; rest as S1
- Expect visited: [..., outcome-stress, gate-stress, outcome-stress, gate-stress, outcome-creation, context-separation, outcome-validation, gate-validation, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: send_back, gate-stress: approve, context-separation: approve, gate-validation: approve]
- Expect terminal: complete
### S6 — Gate 3 reject
- Scripted: gate-stress → reject
- Expect visited: [outcome-research, gate-research, outcome-options, gate-design, outcome-stress, gate-stress]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: reject]
- Expect terminal: rejected
### S7 — Validation loop taken once
- Scripted: gates 1-3 approve; outcome-validation pass 1 → BLOCKED (one BLOCKING finding); outcome-creation reruns with findings; context-separation → new session; outcome-validation pass 2 → VALIDATED WITH WARNINGS; gate-validation → approve
- Expect visited: [..., gate-stress, outcome-creation, context-separation, outcome-validation, outcome-creation, context-separation, outcome-validation, gate-validation, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: approve, context-separation: approve, context-separation: approve, gate-validation: approve]
- Expect terminal: complete (loop counter = 1)
### S8 — Validation loop exhausted
- Scripted: outcome-validation → BLOCKED on passes 1, 2, 3 (and the post-budget pass)
- Expect visited: [..., gate-stress, outcome-creation, context-separation, outcome-validation, (outcome-creation, context-separation, outcome-validation) ×3]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: approve, context-separation: approve ×4]
- Expect terminal: blocked (iteration_limit_reached; best reading — exhaustion route UNSTATED, prose suggests an ABANDON decision by a person)
### S9 — Gate 4 BLOCKED sends back to creation
- Scripted: outcome-validation → VALIDATED; gate-validation → send_back (BLOCKED); outcome-creation, context-separation, outcome-validation rerun → VALIDATED; gate-validation → approve
- Expect visited: [..., outcome-validation, gate-validation, outcome-creation, context-separation, outcome-validation, gate-validation, {tail-decisions | tail-documentation}, sequence-complete]
- Expect gates: [gate-research: approve, gate-design: approve, gate-stress: approve, context-separation: approve, gate-validation: send_back, context-separation: approve, gate-validation: approve]
- Expect terminal: complete
### S10 — Context separation not honoured
- Scripted: context-separation → same session id as outcome-creation
- Expect visited: [..., outcome-creation, context-separation]
- Expect gates: [..., context-separation: waiting]
- Expect terminal: none — run waits on a person (best reading; failure behaviour UNSTATED)
### S11 — Handoff validation fails (no policy declared)
- Scripted: outcome-creation → complete with 2 lens files (protocol 4: "Exactly 3 lens files exist")
- Expect visited: [..., outcome-creation]
- Expect terminal: blocked (best reading; HANDOFF_PROTOCOL.md declares no on_failure — default UNSTATED)
### S12 — Tail failure blocks completion
- Scripted: S1; tail-decisions → failed
- Expect visited: [..., gate-validation, {tail-decisions | tail-documentation}]
- Expect terminal: blocked

## Ambiguities for the process owner
- Loop exhaustion (after max_iterations 3) has no declared route or verdict; prose says "Repeat until VALIDATED or decision to ABANDON", implying an unbudgeted person decision.
- Whether the loop counter counts BLOCKED validations or creation reruns, and whether gate-4 BLOCKED send-backs share that budget, is UNSTATED.
- `loop` on an outcome node creates a cycle; DAG_SCHEMA_SPECIFICATION DAG-06 requires sequence DAGs to be acyclic, and `loop` is not a schema field.
- Node types `checkpoint` and `terminal`, and fields `enforcement`, `instructions`, `tail`, `parallel_with`, `outputs` are outside the DAG schema; `context-separation-requirement` sits in `gates` with a different shape (`type: enforcement_checkpoint`).
- Context separation is manual; what happens when verification (different session id) fails is UNSTATED.
- Gate REVISE targets and budgets UNSTATED; gate-3 REVISE says "iterate design", which could mean outcome-options rather than outcome-stress.
- Gate-4 vocabulary PROCEED/BLOCKED differs from gates 1-3 PROCEED/REVISE/REJECT; no REJECT at gate 4.
- Handoffs are prose protocol, not HANDOFF_CONTRACT.yaml: no on_failure (block/warn/skip), no retry, validations are sentences. Transition 1 validation "Necessity is validated (not rejected)" duplicates gate-1 with no route if it fails.
- Handoff transition ids (research-synthesis, options-analysis, stress-testing) differ from DAG node ids (outcome-research, outcome-options, outcome-stress); transition 5 targets a pseudo node `tail_outcomes`.
- GATE 1 SEQUENCE.md criteria (5, incl. gap analysis) differ from DAG criteria (4, incl. "No unaddressed escalation concerns"); GATE 3 similarly differs.
- SEQUENCE.md comparison table says methodology-change has "3 core + 2 tail", no options analysis and no stress testing — stale against methodology-change v4.
- No SEQUENCE.yaml; `sequence_type` absent from DAG metadata. Terminal verdict names beyond completion UNSTATED.
