# research — methodology sequence

Source: methodology/sequences/research/SEQUENCE.yaml, methodology/sequences/research/SEQUENCE.md, methodology/sequences/research/HANDOFF_PROTOCOL.md (schema meaning: methodology/studios/STUDIO_SCHEMA.md §SEQUENCE.yaml, methodology/CREATING_SEQUENCES.md §Tail Outcomes)
Purpose: Run one research-synthesis outcome, have a person approve the findings, then record decisions and sync documentation as tail outcomes.
Use cases: UC-SEQUENCE, UC-CALL, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-PARALLEL, UC-JOIN, UC-OPTIONAL-BRANCH, UC-HANDOFF, UC-STOP-NAMED, UC-EXEC-POLICY, UC-SEED-ARTIFACTS, UC-CRITICALITY

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 research-synthesis | outcome | Gathers evidence, runs the three-lens review, writes synthesis, extracts knowledge | — / topic → RESEARCH_SYNTHESIS.md, lenses/*/SIGN_OFF.md, product/knowledge/*, HANDOFF.md | UNSTATED ("Core research-synthesis is mandatory") |
| GATE 1 — Research Complete | gate (user_approval) | Person approves findings before tails | research-synthesis / RESEARCH_SYNTHESIS.md, SIGN_OFF.md, knowledge entries → decision | UNSTATED |
| tail-1 decision-recording | outcome (tail) | Writes an ADR for decisions surfaced by the research | GATE 1 / RESEARCH_SYNTHESIS.md, decisions_made, decision_type, rationale → ADR | UNSTATED (skippable) |
| tail-2 documentation-sync | outcome (tail) | Updates documents affected by findings | GATE 1 / RESEARCH_SYNTHESIS.md, affected_artifacts, change_summary, knowledge_entries → doc updates | UNSTATED (skippable) |

## Routes, gates, loops and contracts as declared
- Sequence type: `guided` (SEQUENCE.yaml, SEQUENCE.md) → deviation policy guided: tails may be skipped "if explicitly justified", rationale documented.
- No DAG.yaml; order is the `steps` list (one step). No join rules declared; tail join is implicit on GATE 1 approval.
- `gate_after` on step 1: name "GATE 1 — Research Complete", type `user_approval`.
  - Criteria (SEQUENCE.md prose): RESEARCH_SYNTHESIS.md exists with SCQA framing; all three lenses signed off; knowledge extracted to product/knowledge/; at least 3 sources with credibility tiers; contradictions documented; recommendations actionable.
  - Decision options (prose): PROCEED → approve → tails; REVISE ("Need more evidence or analysis") → send_back, target UNSTATED (best reading: re-run research-synthesis); REJECT ("Research question cannot be answered, abandon") → reject → terminal.
  - Revise budget: UNSTATED. on_failure field: not used (sequence gates have none).
- Tail outcomes: `[decision-recording, documentation-sync]`; SEQUENCE.md `trigger: on_success`, `parallel: true` → parallel group after gate approval.
- Tail skip conditions (HANDOFF_PROTOCOL.md): decision-recording skipped when "No decisions were made during research"; documentation-sync skipped when "No existing documentation affected by research". Orchestrator "checks skip conditions before executing each tail outcome"; skip recorded in HANDOFF.md.
- Tail failure: STUDIO_SCHEMA says tail failure "does not fail the sequence".
- Handoffs (HANDOFF_PROTOCOL.md, not HANDOFF_CONTRACT.yaml):
  - research-synthesis → decision-recording: required_artifacts [RESEARCH_SYNTHESIS.md]; context_keys decisions_made, decision_type, rationale; validation "At least one decision identified OR explicit 'no decisions' rationale"; on_failure UNSTATED.
  - research-synthesis → documentation-sync: required_artifacts [RESEARCH_SYNTHESIS.md]; context_keys affected_artifacts, change_summary, knowledge_entries; validation "Affected artifacts identified OR explicit 'no docs affected' rationale"; on_failure UNSTATED.
- Loops, spirals, triads at sequence level: none (the three-lens triad lives inside research-synthesis).

## Scenarios
### S1 — Approved, both tails run
- Inputs: topic="rate-limiting-patterns"
- Scripted: research-synthesis → complete (writes RESEARCH_SYNTHESIS.md, decisions_made=[1], affected_artifacts=[1]); GATE 1 → approve; decision-recording → complete; documentation-sync → complete
- Expect visited: [research-synthesis, GATE 1, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1 — Research Complete: approve]
- Expect terminal: complete

### S2 — Sent back once, then approved
- Inputs: topic="visual-design-principles"
- Scripted: research-synthesis → complete; GATE 1 → send_back ("need more evidence"); research-synthesis → complete; GATE 1 → approve; both tails → complete
- Expect visited: [research-synthesis, GATE 1, research-synthesis, GATE 1, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: send_back, GATE 1: approve]
- Expect terminal: complete

### S3 — Rejected
- Inputs: topic="unanswerable-question"
- Scripted: research-synthesis → complete; GATE 1 → reject
- Expect visited: [research-synthesis, GATE 1]
- Expect gates: [GATE 1: reject]
- Expect terminal: rejected (name UNSTATED; prose "abandon")

### S4 — No decisions: decision-recording skipped
- Inputs: topic="competitive-analysis-2026"
- Scripted: research-synthesis → complete (HANDOFF.md skip decision-recording=true, "No decisions made"); GATE 1 → approve; documentation-sync → complete
- Expect visited: [research-synthesis, GATE 1, documentation-sync] (decision-recording recorded skipped)
- Expect gates: [GATE 1: approve]
- Expect terminal: complete

### S5 — Both tails skipped
- Inputs: topic="quick-survey"
- Scripted: research-synthesis → complete (both skip flags true with rationale); GATE 1 → approve
- Expect visited: [research-synthesis, GATE 1] (both tails skipped)
- Expect gates: [GATE 1: approve]
- Expect terminal: complete

### S6 — Tail fails, sequence still completes
- Inputs: topic="rate-limiting-patterns"
- Scripted: research-synthesis → complete; GATE 1 → approve; decision-recording → complete; documentation-sync → failed
- Expect visited: [research-synthesis, GATE 1, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve]
- Expect terminal: complete (documentation-sync recorded failed)

### S7 — Handoff missing RESEARCH_SYNTHESIS.md
- Inputs: topic="rate-limiting-patterns"
- Scripted: research-synthesis → complete but RESEARCH_SYNTHESIS.md absent; handoff validation fails (on_failure UNSTATED; best reading block, the standard's value for critical transitions); gate criteria also unmet
- Expect visited: [research-synthesis]
- Expect gates: []
- Expect terminal: blocked (best reading)

## Ambiguities for the process owner
- REVISE target and revise budget are unstated; runtime gate vocabulary is APPROVED|REJECTED only (STUDIO_SCHEMA), so REVISE has no machine route.
- Terminal verdict names (complete / rejected / blocked) are not declared.
- Handoff on_failure policy is not declared (HANDOFF_PROTOCOL.md has no `validation.on_failure`); validations are prose.
- Tail order: SEQUENCE.md and STUDIO_SCHEMA say parallel; CREATING_SEQUENCES.md says tails "execute in order" and chain HANDOFF.md from decision-recording to documentation-sync.
- Diagram in SEQUENCE.md draws tails triggered by research-synthesis `on_success`, while the gate text says tails follow GATE 1 approval.
- Skip conditions are prose read from HANDOFF.md, not a state field; who decides the flag is unstated.
- No criticality declared on any step.
