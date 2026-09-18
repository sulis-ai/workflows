# studio-creation — methodology sequence

Source: methodology/sequences/studio-creation/SEQUENCE.yaml, methodology/sequences/studio-creation/SEQUENCE.md (schema meaning: methodology/studios/STUDIO_SCHEMA.md)
Purpose: Create a studio definition under triad governance, have a person approve it, wire it into the platform inline, then record decisions and sync docs.
Use cases: UC-SEQUENCE, UC-CALL, UC-EXEC-POLICY, UC-OPTIONAL-BRANCH, UC-PATHS, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-PARALLEL, UC-HANDOFF, UC-STOP-NAMED, UC-LENS-TRIAD, UC-TOOL-RUNNER

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 studio-definition | outcome | Writes the 7-file studio bundle via its 15-step process and Studio Architecture Triad | — / slug, mode (creation/extraction), domain input → methodology/studios/{slug}/*, synthesis/APPROVAL_REQUEST.md, lenses/*/ANALYSIS.md, synthesis/TENSION_REPORT.md | UNSTATED |
| GATE 1 — Studio Definition Approved | gate (user_approval) | Person approves the bundle | studio-definition / bundle + approval request → decision | UNSTATED |
| 2 integration | step (inline, not an outcome; commented out of SEQUENCE.yaml) | Agent pointer, studio index, sequence registry, outcome registration; extraction-mode extras | GATE 1 / slug, file paths, mode, lens verdicts → .claude/agents/{slug}.yaml, studios/index.md, sequences/index.md | UNSTATED ("Guided allows skipping the integration step") |
| decision-recording | outcome (tail) | ADR for studio creation decisions | integration / ADR content → ADR | UNSTATED |
| documentation-sync | outcome (tail) | Updates METHODOLOGY.md, CREATING_SEQUENCES.md, ARCHITECTURE.md | integration / affected documentation list → doc updates | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `guided`. SEQUENCE.yaml declares only step 1 plus a comment: "Step 2: integration (inline … ) Not a formal OFM outcome; executed as inline tasks."
- Order (SEQUENCE.md): studio-definition → GATE 1 → integration → tails.
- GATE 1: `gate_after`, type `user_approval`. Criteria (prose): 7 files present and schema-compliant; DOMAIN_RESEARCH.md 5+ sources, 2+ Tier 1-2; STANDARDS.md specificity gradient > 3.0, substitution test < 50%; 5-8 anti-patterns, 3+ from research; PD-01..PD-06 satisfied; disclosure ordering acyclic with 2+ roots; all 3 lens verdicts PROCEED; pre-gate compliance 14/14 PASS; no TODO/TBD.
  - PROCEED → approve → integration; REVISE → send_back to studio-definition ("iterate studio-definition"), budget UNSTATED; REJECT → reject ("Studio not viable, abandon sequence").
- Integration internal branches (prose, flag-driven):
  - Sequence Registry: "If the studio declares sequences in STUDIO.yaml" → update sequences/index.md; else skip.
  - Outcome Registration: "If the studio declares owned outcomes in STUDIO.yaml" → verify DRAFT placeholders / active OUTCOME.md exist; else skip.
  - Mode `extraction` → additionally set absorbs_function, add source_ref, document function→studio mapping; mode `creation` → not.
- Integration skip: "Guided allows skipping the integration step if only the definition needs updating."
- Tails: `trigger: on_success`, `parallel: true`, after "core chain completes".
- Handoffs (SEQUENCE.md table only; no contract file): studio-definition → integration (slug, file paths, mode, lens verdicts); integration → tails (ADR content, affected documentation list). required_outputs as files and on_failure: UNSTATED.
- Lens triad (Domain Analyst, Structure Critic, Practicality Assessor) is inside studio-definition; the gate reads its verdicts. No sequence-level loops or spirals.

## Scenarios
### S1 — Creation mode, approved, integration with registries, tails run
- Inputs: slug="quality-governance", mode="creation"; STUDIO.yaml declares sequences and owned outcomes
- Scripted: studio-definition → complete (3 lens verdicts PROCEED); GATE 1 → approve; integration → complete (pointer, index, sequence registry, outcome registration); both tails → complete
- Expect visited: [studio-definition, GATE 1, integration, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1 — Studio Definition Approved: approve]
- Expect terminal: complete

### S2 — Sent back once, then approved
- Inputs: slug="quality-governance", mode="creation"
- Scripted: studio-definition → complete; GATE 1 → send_back ("anti-patterns below 5"); studio-definition → complete; GATE 1 → approve; integration → complete; tails → complete
- Expect visited: [studio-definition, GATE 1, studio-definition, GATE 1, integration, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: send_back, GATE 1: approve]
- Expect terminal: complete

### S3 — Rejected
- Inputs: slug="not-a-domain", mode="creation"
- Scripted: studio-definition → complete; GATE 1 → reject
- Expect visited: [studio-definition, GATE 1]
- Expect gates: [GATE 1: reject]
- Expect terminal: rejected (name UNSTATED; "abandon sequence")

### S4 — Extraction mode, no sequences or owned outcomes declared
- Inputs: slug="product-development", mode="extraction"; STUDIO.yaml declares no sequences, no owned outcomes
- Scripted: studio-definition → complete; GATE 1 → approve; integration → complete (pointer with source_ref, index, absorbs_function, mapping; registry and outcome registration skipped)
- Expect visited: [studio-definition, GATE 1, integration, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve]
- Expect terminal: complete

### S5 — Integration skipped (definition-only update)
- Inputs: slug="quality-governance", mode="creation", skip=[integration] with rationale
- Scripted: studio-definition → complete; GATE 1 → approve; tails → complete
- Expect visited: [studio-definition, GATE 1, {decision-recording | documentation-sync}] (integration recorded skipped)
- Expect gates: [GATE 1: approve]
- Expect terminal: complete

### S6 — Tail fails, sequence still completes
- Inputs: slug="quality-governance", mode="creation"
- Scripted: as S1; decision-recording → failed
- Expect visited: [studio-definition, GATE 1, integration, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve]
- Expect terminal: complete (decision-recording recorded failed, per STUDIO_SCHEMA tail rule)

## Ambiguities for the process owner
- The integration step is not machine-declared: SEQUENCE.yaml has it only as a comment, and STUDIO_SCHEMA `steps` accept outcomes only, so an engine reading SEQUENCE.yaml would go straight from GATE 1 to tails.
- Integration's conditional sub-tasks ("If the studio declares sequences…", mode = extraction) are prose; no field or condition expresses them.
- How integration is skipped under guided mode is unstated (it is not marked `optional`).
- REVISE budget unstated; runtime gate vocabulary APPROVED|REJECTED has no send-back.
- Handoff contents are a prose table; no required outputs, validation or on_failure.
- Terminal verdict names and step criticality are not declared.
- SEQUENCE.md says tails parallel; CREATING_SEQUENCES.md says tails run in order.
