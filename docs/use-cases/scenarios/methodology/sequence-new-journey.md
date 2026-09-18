# new-journey — methodology sequence

Source: methodology/sequences/new-journey/SEQUENCE.yaml (v1.0.0, status deprecated), methodology/sequences/new-journey/DAG.yaml (v1.0.0), methodology/sequences/new-journey/HANDOFF_CONTRACT.yaml (v1.0.0), methodology/sequences/new-journey/SEQUENCE.md (v2.0.0, deprecated in favour of journey-lifecycle)
Purpose: Validate a user journey from market evidence through framing options, full journey definition and stress testing, with two person gates and two parallel tail outcomes after the final gate.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-HANDOFF, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-PARALLEL, UC-JOIN, UC-CALL-GATES, UC-CRITICALITY, UC-STOP-NAMED, UC-VERSION

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| outcome-research-synthesis | outcome | Market evidence, 5+ signals, credibility tiers | — → RESEARCH_SYNTHESIS.md, RECOMMENDATION.md, lenses/*/ANALYSIS.md | standard |
| outcome-options-analysis | outcome | Compare ≥2 framing approaches, screen anti-goals | research-synthesis → OPTIONS_ANALYSIS.md, lenses/*/ANALYSIS.md | standard |
| gate-01 | gate | Research & Framing Approval | options-analysis → decision | critical |
| outcome-journey-definition | outcome | Full JDD; GATE 0 (Journey Readiness) internal | gate-01 → JOURNEY.md, MARKET_EVIDENCE.md, CAPABILITY_MAP.md, GAP_ANALYSIS.md, MILESTONES.md, FEATURES.md | critical |
| outcome-stress-testing | outcome | Adversarial validation, ≥2 ARC cycles | journey-definition → STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md | standard |
| gate-02 | gate | Journey Approval | stress-testing → decision | critical |
| tail-decision-recording | outcome (tail) | ADRs for scope/persona choices | gate-02 → ADR-*.md | standard |
| tail-documentation-sync | outcome (tail) | Update journey registry, roadmap, docs | gate-02 → DOCUMENTATION_PROPOSAL.md | standard |
| sequence-complete | terminal | End | both tails (default all_success) | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict`. Linear chain; no routing, edges or loops.
- SEQUENCE.yaml `gate_after`: step 2 options-analysis → "GATE 1 — Research & Framing Approval" (user_approval); step 4 stress-testing → "GATE 2 — Journey Approval" (user_approval). Agrees with DAG.
- `gates.gate-research-framing-approval`: 6 criteria (5+ signals, confidence ≥ MEDIUM, three lens sign-offs, ≥2 framings, rationale, no anti-goal violations), `approval_required: true`, decisions PROCEED | REVISE | REJECT. on_failure, REVISE target, budget: UNSTATED.
- `gates.gate-journey-approval`: 8 criteria (six artifacts, stress-test report, Kano classification), decisions PROCEED | REVISE | REJECT. on_failure, REVISE target, budget: UNSTATED.
- GATE 0 inside journey-definition → child gate (UC-CALL-GATES); decisions UNSTATED here.
- Tails depend directly on gate-02 (no final regular outcome between); `tail: true`, `parallel_with`; SEQUENCE.md `trigger: on_success, parallel: true`. sequence-complete: default all_success.
- Handoff contracts:
  1. research-synthesis → options-analysis: RESEARCH_SYNTHESIS.md, RECOMMENDATION.md, `research_findings` (array minItems 1) → `block`, retry max_attempts 1, backoff none.
  2. options-analysis → journey-definition (via gate-01): OPTIONS_ANALYSIS.md, `selected_approach` {recommendation, rationale}; constraint RES-FRAMING-COMPLETE binding → `block`, retry 1.
  3. journey-definition → stress-testing: six journey artifacts (exists) + `journey_summary` {journey_name, steps_count, capabilities_count, gaps_count, kano_classification} → `block`.
  4a. stress-testing → decision-recording (via gate-02): STRESS_TEST_REPORT.md, `stress_test_results` {verdict ∈ PASS|CONDITIONAL|FAIL, failure_modes}; constraints JOURNEY-APPROVED, STRESS-TESTED binding → `warn`.
  4b. stress-testing → documentation-sync: same outputs; expected input `documentation_changes` `required: false` → `warn`.

## Scenarios
### S1 — Happy path
- Inputs: journey_name="founder-onboarding", offering="studios"
- Scripted: all outcomes → complete; GATE 0 internal → approve; gate-01 → approve (PROCEED); gate-02 → approve (PROCEED); contracts satisfied
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-journey-definition, outcome-stress-testing, gate-02, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S2 — Gate 1 send back once
- Scripted: gate-01 → send_back (REVISE); rerun outcome-options-analysis (best reading); gate-01 → approve; rest as S1
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-options-analysis, gate-01, outcome-journey-definition, outcome-stress-testing, gate-02, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: send_back, gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S3 — Gate 1 reject
- Scripted: gate-01 → reject
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01]
- Expect gates: [gate-01: reject]
- Expect terminal: rejected
### S4 — Gate 2 send back once
- Scripted: gate-02 → send_back; rerun outcome-journey-definition, outcome-stress-testing (best reading); gate-02 → approve
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-journey-definition, outcome-stress-testing, gate-02, outcome-journey-definition, outcome-stress-testing, gate-02, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: send_back, gate-02: approve]
- Expect terminal: complete
### S5 — Gate 2 reject (no tails run)
- Scripted: gate-02 → reject
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-journey-definition, outcome-stress-testing, gate-02]
- Expect gates: [gate-01: approve, gate-02: reject]
- Expect terminal: rejected
### S6 — Handoff `block`: research findings empty
- Scripted: outcome-research-synthesis → complete; `research_findings` = [] (violates minItems 1); one attempt
- Expect visited: [outcome-research-synthesis]
- Expect gates: []
- Expect terminal: blocked
### S7 — Handoff `block`: journey package incomplete
- Scripted: gate-01 → approve; outcome-journey-definition → complete without MILESTONES.md
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-journey-definition]
- Expect gates: [gate-01: approve]
- Expect terminal: blocked ("Journey definition must be complete before stress-testing can begin")
### S8 — Handoff `warn` into tails, optional input absent
- Scripted: S1; `stress_test_results` missing `failure_modes`; `documentation_changes` not supplied
- Expect visited: as S1
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete (warnings recorded; optional input visibly absent)
### S9 — Tail failure blocks completion
- Scripted: S1; tail-documentation-sync → failed
- Expect visited: [outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-journey-definition, outcome-stress-testing, gate-02, {tail-decision-recording | tail-documentation-sync}]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: blocked

## Ambiguities for the process owner
- Deprecated in both SEQUENCE.yaml and SEQUENCE.md but still executable; engine behaviour for deprecated sequences UNSTATED.
- Gate REVISE targets, redo budgets and on_failure UNSTATED; S2/S4 targets are best readings.
- Contract 4a/4b `from: stress-testing` skips the gate-02 and routes straight to tails; binding constraint JOURNEY-APPROVED implies the gate, but the `warn` policy means a missing stress-test report does not stop tails even though gate-02 criteria require it.
- Contract 4a `expected_inputs.adr_context.maps_to: "journey scope and persona decisions"` and 4b `maps_to: "journey artifacts"` are prose, not output names.
- Contract 3 `maps_to` is a list — not allowed by the standard (string).
- `stress_test_results.verdict: FAIL` has no declared route before gate-02.
- Stress-testing criticality `standard` while journey-definition is `critical`; SEQUENCE.md says strict (all must run) — meaning of `standard` in a strict sequence UNSTATED.
- GATE 0 internal to journey-definition: surfacing UNSTATED.
- Node type `terminal`, `tail`, `parallel_with`, `outputs` outside DAG schema; SEQUENCE.yaml tail_outcomes is a flat list without the parallel/on_success semantics.
- Terminal verdict names beyond completion UNSTATED.
- HANDOFF_CONTRACT.yaml contracts 4a/4b have malformed schema indentation (`properties:` followed directly by `type:` under failure_modes items).
