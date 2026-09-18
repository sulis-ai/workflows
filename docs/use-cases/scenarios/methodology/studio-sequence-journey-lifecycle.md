# journey-lifecycle — methodology studio sequence

Source: methodology/studios/product-development/sequences/journey-lifecycle/SEQUENCE.yaml, methodology/delivery/product/SEQUENCES.md §journey-lifecycle and §YAML Definition, methodology/studios/product-development/STUDIO.yaml (schema meaning: methodology/studios/STUDIO_SCHEMA.md)
Purpose: Produce a validated, market-evidence-driven user journey: research, framing options, journey definition and stress-testing, with two approvals and mandatory tails.
Use cases: UC-SEQUENCE, UC-CALL, UC-CALL-GATES, UC-EXEC-POLICY, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-PARALLEL, UC-HANDOFF, UC-STOP-NAMED

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 research-synthesis | outcome | Market evidence gathering, three-lens review | — / journey name → RESEARCH_SYNTHESIS.md | UNSTATED |
| 2 options-analysis | outcome | Compares journey framing approaches | research-synthesis / market evidence, problem validation status → OPTIONS_ANALYSIS.md | UNSTATED |
| GATE 1 — Research & Framing Approval | gate (user_approval) | Person approves problem evidence and framing | options-analysis / RESEARCH_SYNTHESIS.md, OPTIONS_ANALYSIS.md → decision | UNSTATED |
| 3 journey-definition | outcome (contains internal "GATE 0") | Full journey definition, capability mapping, gap analysis | GATE 1 / selected framing, rejected alternatives, GATE 1 constraints → JOURNEY.md, MARKET_EVIDENCE.md, CAPABILITY_MAP.md, GAP_ANALYSIS.md, MILESTONES.md, FEATURES.md | UNSTATED |
| 4 stress-testing | outcome | Adversarial validation of the journey | journey-definition / journey package → stress-test report | UNSTATED |
| GATE 2 — Journey Approval | gate (user_approval) | Person approves the journey | stress-testing / journey package + stress report → decision | UNSTATED |
| decision-recording | outcome (tail, mandatory) | ADR for decisions | GATE 2 / decisions made → ADR | UNSTATED |
| documentation-sync | outcome (tail, mandatory) | Doc updates | GATE 2 / documentation needs → doc updates | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict`: "All outcomes must execute in order"; "Deviation requires explicit approval". No optional steps.
- Linear order from `steps`: research-synthesis → options-analysis → GATE 1 → journey-definition → stress-testing → GATE 2 → tails.
- GATE 1 (`gate_after` step 2, `user_approval`), criteria (SEQUENCES.md): RESEARCH_SYNTHESIS.md shows problem existence (5+ independent signals); market evidence confidence MEDIUM+; OPTIONS_ANALYSIS.md compares 2+ framings; selected framing has evidence-based rationale; no anti-goal violations; all three research lenses signed off.
- GATE 2 (`gate_after` step 4, `user_approval`), criteria: JOURNEY.md clear goal, steps, success criteria; MARKET_EVIDENCE.md 5+ sources; CAPABILITY_MAP.md all required capabilities; GAP_ANALYSIS.md maps gaps to features; MILESTONES.md measurable; FEATURES.md links features to gaps; stress-test report validates assumptions; Kano classification assigned.
- Gate decisions: none declared in SEQUENCES.md. Runtime (STUDIO_SCHEMA): resume on APPROVED; `REJECTED` accepted. Send-back: not declared.
- Internal gate: journey-definition has "GATE 0 internal" → a child gate that must surface to the person.
- Tails: `trigger: on_success`, `parallel: true`; strict-mode rules: "Tail outcomes execute automatically on success (C-05 compliance)"; "Tail outcomes are mandatory, not optional (C-05-E1)".
- Handoffs (prose table; "Function-level sequences embed handoff contracts in their gate criteria"): research-synthesis → options-analysis (market evidence, validation status, key findings, credibility); options-analysis → journey-definition (selected framing, rejected alternatives, evidence base, GATE 1 constraints); journey-definition → stress-testing (the six-file journey package); stress-testing → tails (validated journey, report, decisions, doc needs). on_failure UNSTATED.
- No loops, spirals or triads at sequence level.

## Scenarios
### S1 — Both gates approved, tails run
- Inputs: journey_name="first-time-founder-onboarding"
- Scripted: research-synthesis → complete; options-analysis → complete; GATE 1 → approve; journey-definition → complete (internal GATE 0 → approve); stress-testing → complete; GATE 2 → approve; both tails → complete
- Expect visited: [research-synthesis, options-analysis, GATE 1, journey-definition, stress-testing, GATE 2, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1 — Research & Framing Approval: approve, journey-definition/GATE 0: approve, GATE 2 — Journey Approval: approve]
- Expect terminal: complete

### S2 — Rejected at GATE 1 (framing not approved)
- Inputs: journey_name="weak-signal-journey"
- Scripted: research-synthesis → complete; options-analysis → complete; GATE 1 → reject
- Expect visited: [research-synthesis, options-analysis, GATE 1]
- Expect gates: [GATE 1: reject]
- Expect terminal: rejected (name UNSTATED)

### S3 — Rejected at GATE 2
- Inputs: journey_name="first-time-founder-onboarding"
- Scripted: as S1 to stress-testing; GATE 2 → reject
- Expect visited: [research-synthesis, options-analysis, GATE 1, journey-definition, stress-testing, GATE 2]
- Expect gates: [GATE 1: approve, journey-definition/GATE 0: approve, GATE 2: reject]
- Expect terminal: rejected

### S4 — Child gate inside journey-definition waits on the person
- Inputs: journey_name="first-time-founder-onboarding"
- Scripted: GATE 1 → approve; journey-definition reaches internal GATE 0 → no decision yet
- Expect visited: [research-synthesis, options-analysis, GATE 1, journey-definition]
- Expect gates: [GATE 1: approve, journey-definition/GATE 0: pending]
- Expect terminal: awaiting person (run paused, not auto-approved)

### S5 — Tail fails after approval
- Inputs: journey_name="first-time-founder-onboarding"
- Scripted: as S1; documentation-sync → failed
- Expect visited: [research-synthesis, options-analysis, GATE 1, journey-definition, stress-testing, GATE 2, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, journey-definition/GATE 0: approve, GATE 2: approve]
- Expect terminal: complete per STUDIO_SCHEMA ("failure does not fail the sequence") — conflicts with "mandatory" tails; see ambiguities

## Ambiguities for the process owner
- No gate decision options (approve / revise / reject) are declared; send-back target and budget absent. Scenarios use approve/reject only, matching the runtime vocabulary.
- Tails are "mandatory, not optional (C-05-E1)" here, but STUDIO_SCHEMA says tail failure never fails a sequence; the verdict when a mandatory tail fails is unstated.
- "Research must demonstrate problem existence before framing" is a rule with no gate or check between steps 1 and 2.
- Internal GATE 0 of journey-definition is named but its decisions and routing live in that outcome, not here.
- Handoffs are prose; no required outputs as files, validation or on_failure policy.
- Terminal verdict names and criticality not declared.
