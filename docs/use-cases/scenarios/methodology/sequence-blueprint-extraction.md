# blueprint-extraction — methodology sequence

Source: methodology/sequences/blueprint-extraction/DAG.yaml, SEQUENCE.yaml, SEQUENCE.md, HANDOFF_PROTOCOL.md
Purpose: Extract an existing organisation's identity, principles, positioning, strategy and commercial model from its materials, with three approval gates and a documentation tail.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-IN-TYPED, UC-HANDOFF, UC-OUT-MULTI, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-REFUSAL-MODE, UC-STOP-NAMED, UC-STOP-HONEST, UC-CRITICALITY, UC-CALL

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| outcome-identity (identity-articulation) | outcome (mode=extraction) | Extract identity | — / materials → IDENTITY.md, BRAND.md, TONE_OF_VOICE.md | standard |
| outcome-principles (principles-codification) | outcome (mode=extraction) | Extract decision principles | outcome-identity / identity artifacts, values_extracted → PRINCIPLES.md | standard |
| gate-foundation "GATE 1 - Foundation Complete" | gate | Person approves foundation | outcome-principles | critical |
| outcome-positioning (strategic-positioning) | outcome (mode=extraction) | Extract vision, anti-goals | gate-foundation / PRINCIPLES.md → VISION.md, ANTI_GOALS.md | standard |
| outcome-strategy (strategy-formulation) | outcome (mode=extraction) | Extract strategic bets | outcome-positioning → STRATEGY.md | standard |
| gate-strategy "GATE 2 - Strategy Complete" | gate | Person approves strategy layer | outcome-strategy | critical |
| outcome-commercial (commercial-validation) | outcome (mode=extraction) | Extract commercial model | gate-strategy / STRATEGY.md → COMMERCIAL.md, BMC.md | standard |
| gate-blueprint "GATE 3 - Blueprint Complete" | gate | Person approves full blueprint | outcome-commercial | critical |
| outcome-documentation (documentation-sync) | outcome (tail: true) | Update methodology/index.md | gate-blueprint | standard |

## Routes, gates, loops and contracts as declared
- DAG `type: sequence`; no `execution` block → default_join_rule all_success (spec default). Every node has ≤1 predecessor, so joins are trivial. No edges, loops, routing.
- SEQUENCE.yaml `type: guided` → deviations allowed with rationale: skip outcome (yes, "Document why materials unavailable"), reorder (no), add (yes), repeat outcome (yes, "After obtaining new materials") → UC-EXEC-POLICY.
- `mode: extraction` passed to every outcome (DAG node field `mode`, SEQUENCE.yaml note) → input on each call.
- Gates (DAG `gates:` block, `approval_required: true`, `on_failure` UNSTATED):
  - gate-foundation-complete criteria: IDENTITY.md with confidence; BRAND.md; TONE_OF_VOICE.md; PRINCIPLES.md with citations; no blocking contradictions. SEQUENCE.md adds "Major gaps flagged for stakeholder validation". Decisions (prose): PROCEED → outcome-positioning; REVISE → "Return to identity or principles for gap filling"; PAUSE → "Obtain additional materials before continuing".
  - gate-strategy-complete criteria: VISION.md WHY/HOW/WHAT; ANTI_GOALS.md cross-refs; STRATEGY.md ≥1 bet; coherent with foundation; confidence documented. Decisions: PROCEED → outcome-commercial; REVISE → "Return to positioning or strategy"; PAUSE.
  - gate-blueprint-complete criteria: COMMERCIAL.md pricing; BMC.md 9 blocks or gaps; coherent; gaps with validation approach; confidence acceptable. Decisions: APPROVE → outcome-documentation; REVISE → "Address specific gaps before finalizing"; ESCALATE → "Significant gaps require stakeholder access".
- Mapping: PROCEED/APPROVE → approve; REVISE → send_back (target person-chosen among the named outcomes); PAUSE → pause (UC-REFUSAL-MODE pause); ESCALATE → terminal escalated (reading).
- Tail: `outcome-documentation` `tail: true`, after gate-blueprint approve; SEQUENCE.yaml `tail_outcomes: [documentation-sync]`.
- Handoffs (HANDOFF_PROTOCOL.md, prose-level contracts, no on_failure policy): identity→principles required IDENTITY.md, BRAND.md, TONE_OF_VOICE.md, context_keys identity_confidence, values_extracted, gaps; principles→positioning PRINCIPLES.md; positioning→strategy VISION.md, ANTI_GOALS.md; strategy→commercial STRATEGY.md; commercial→gate-blueprint COMMERCIAL.md, BMC.md + full_blueprint_confidence. Validations are prose ("IDENTITY.md exists with WHY/WHAT/VALUES sections").
- Missing materials policy (prose): "Document the gap; Continue with available materials; Flag for stakeholder validation in final gate" → outcome completes with gaps, not blocked (UC-STOP-HONEST style).
- No spiral, no lens triads, no retry, no criticality-driven skips beyond guided rules.

## Scenarios
### S1 — Happy path
- Inputs: organization-name=acme-corp, materials=/path/to/acme-materials/, mode=extraction
- Scripted: all five outcomes → complete; gate-foundation → approve; gate-strategy → approve; gate-blueprint → approve; outcome-documentation → complete
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, outcome-commercial, gate-blueprint, outcome-documentation]
- Expect gates: [gate-foundation: approve, gate-strategy: approve, gate-blueprint: approve]
- Expect terminal: complete
### S2 — GATE 1 REVISE back to principles
- Inputs: as S1
- Scripted: identity, principles complete; gate-foundation → send_back (target outcome-principles, "missing citations"); outcome-principles → complete; gate-foundation → approve; rest as S1
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, outcome-commercial, gate-blueprint, outcome-documentation]
- Expect gates: [gate-foundation: send_back, gate-foundation: approve, gate-strategy: approve, gate-blueprint: approve]
- Expect terminal: complete
### S3 — GATE 2 REVISE back to positioning (re-runs strategy)
- Inputs: as S1
- Scripted: to gate-strategy; gate-strategy → send_back (target outcome-positioning); outcome-positioning → complete; outcome-strategy → complete; gate-strategy → approve; rest as S1
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, outcome-positioning, outcome-strategy, gate-strategy, outcome-commercial, gate-blueprint, outcome-documentation]
- Expect gates: [gate-foundation: approve, gate-strategy: send_back, gate-strategy: approve, gate-blueprint: approve]
- Expect terminal: complete
### S4 — GATE 1 PAUSE for more materials, then resume
- Inputs: as S1
- Scripted: identity, principles complete; gate-foundation → pause; (resume with added materials) gate-foundation → approve; rest as S1
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, outcome-commercial, gate-blueprint, outcome-documentation]
- Expect gates: [gate-foundation: pause, gate-foundation: approve, gate-strategy: approve, gate-blueprint: approve]
- Expect terminal: complete
### S5 — GATE 3 ESCALATE
- Inputs: as S1
- Scripted: to gate-blueprint; gate-blueprint → reject (ESCALATE: "significant gaps require stakeholder access")
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, outcome-commercial, gate-blueprint]
- Expect gates: [gate-foundation: approve, gate-strategy: approve, gate-blueprint: escalate]
- Expect terminal: escalated
### S6 — Guided skip: no commercial materials
- Inputs: as S1, materials lack pricing/contracts; skip rationale "materials unavailable"
- Scripted: outcome-commercial → skipped (documented); gate-blueprint → approve; documentation → complete
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy, gate-strategy, gate-blueprint, outcome-documentation]
- Expect gates: [gate-foundation: approve, gate-strategy: approve, gate-blueprint: approve]
- Expect terminal: complete (skip recorded with rationale)
### S7 — Handoff missing STRATEGY.md
- Inputs: as S1
- Scripted: outcome-strategy → complete without STRATEGY.md → handoff validation fails (policy UNSTATED; reading: block)
- Expect visited: [outcome-identity, outcome-principles, gate-foundation, outcome-positioning, outcome-strategy]
- Expect gates: [gate-foundation: approve]
- Expect terminal: blocked

## Ambiguities for the process owner
- Gate `on_failure` UNSTATED in DAG; gate vocabularies differ per gate (PROCEED/REVISE/PAUSE vs APPROVE/REVISE/ESCALATE) and none maps to the schema's REVISE|REJECT.
- REVISE targets are a choice between two named outcomes ("identity or principles"); which one, and whether downstream outcomes re-run, is UNSTATED. Redo budget UNSTATED.
- ESCALATE and PAUSE have no declared route or terminal; S4/S5 are readings.
- HANDOFF_PROTOCOL.md has no on_failure policy for any transition; validations are prose only.
- Guided "Skip outcome" conflicts with extraction rule "Continue with available materials" (does a missing-materials outcome skip or complete with gaps?). Skipping outcome-commercial leaves gate-blueprint with a skipped predecessor under all_success — would block unless skip counts.
- Gate-1 criterion "Major gaps flagged for stakeholder validation" is in SEQUENCE.md only, not DAG `gates`.
- Tail "Tail outcomes are skipped if explicitly not needed" (standard) vs no skip condition declared here.
- `produces` and `mode` are node fields not in DAG_SCHEMA_SPECIFICATION; the spec's `provides/requires` are unused.
- synthesis/BLUEPRINT_SUMMARY.md and "Confidence Aggregation at each gate" are described but no node produces them.
- Minimum viable input "At least 2-3 materials per outcome" is not a declared input check.
