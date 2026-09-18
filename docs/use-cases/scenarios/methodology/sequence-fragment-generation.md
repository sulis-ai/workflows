# fragment-generation — methodology sequence

Source: methodology/sequences/fragment-generation/DAG.yaml, SEQUENCE.yaml, SEQUENCE.md
Purpose: Identify magic moments in the product experience artifacts, get them approved, then generate one screen fragment per approved moment.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-IN-TYPED, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-FOREACH, UC-CALL, UC-RETRY, UC-STOP-NAMED, UC-CRITICALITY

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| identify-moments | outcome | Scan product/experience/ with 4-test filter (pass 3 of 4), classify by surface | — / SURFACE_MAP.md, INFORMATION_ARCHITECTURE.md, EXPERIENCE_JOURNEYS.md, PERSONAS.md → product/experience/fragments/MOMENTS.md | standard |
| gate-01 "Moments Approval" | gate (user_approval) | Person approves all, a subset, revises or rejects | identify-moments / MOMENTS.md → approved moment set | critical |
| generate-fragments | for_each over approved moments → outcome compliant-mockup-production (screen_fragment) | One fragment per moment, DAV-validated | gate-01 / moment_id, surface, scenario → product/experience/fragments/{fragment-id}.html | standard |
| sequence-complete | terminal | End | generate-fragments | UNSTATED |

## Routes, gates, loops and contracts as declared
- DAG `type: sequence`, linear, no execution block → default all_success (no multi-predecessor nodes). No edges, routing, spirals, triads, handoff contract file.
- `sequence_type: guided` (DAG metadata) / `type: guided` (SEQUENCE.yaml).
- Default inputs (SEQUENCE.md): artifact_paths `product/experience/`; filter 4-test; classification by surface; threshold 3 of 4; output location. Optional `--surface <name>` invocation filter.
- gate-moments-approval: `approval_required: true`; criteria: MOMENTS.md exists at path; each moment passes ≥3 of 4 tests; classified by surface; no duplicates across surfaces. `decisions: [PROCEED, PROCEED_WITH_SUBSET, REVISE, REJECT]`:
  - PROCEED → generate-fragments over all moments (approve).
  - PROCEED_WITH_SUBSET → generate-fragments over selected moments (approve with input: selection).
  - REVISE → "Re-run identification with adjusted criteria" → send_back to identify-moments (budget UNSTATED).
  - REJECT → "Abandon" → terminal rejected.
  - Gate prose also: "User may add, remove, or re-prioritise moments" → input-style edits at the gate.
- For-each: SEQUENCE.yaml "fan-out: one invocation per moment in MOMENTS.md"; DAG agent_instructions "Fragments are generated sequentially — one CMP invocation per moment" → for_each with concurrency 1.
- Per-item retry: "If a fragment fails DAV, fix and retry before moving to next moment" → retry on DAV failure, max attempts UNSTATED.
- Handoff (prose table only): identify-moments → CMP: MOMENTS.md with moment IDs, surfaces, scenarios, significance ratings; on_failure UNSTATED.

## Scenarios
### S1 — PROCEED with all moments
- Inputs: context=product-experience; product/experience/ contains the four source docs; MOMENTS.md yields [m1 consumer, m2 consumer, m3 marketing]
- Scripted: identify-moments → complete; gate-01 → approve (PROCEED); CMP[m1], CMP[m2], CMP[m3] → complete (DAV pass)
- Expect visited: [identify-moments, gate-01, generate-fragments[m1], generate-fragments[m2], generate-fragments[m3], sequence-complete]
- Expect gates: [gate-01: approve]
- Expect terminal: complete
### S2 — PROCEED WITH SUBSET
- Inputs: as S1
- Scripted: identify-moments → complete; gate-01 → approve (PROCEED_WITH_SUBSET, selection=[m3]); CMP[m3] → complete
- Expect visited: [identify-moments, gate-01, generate-fragments[m3], sequence-complete]
- Expect gates: [gate-01: approve(subset=[m3])]
- Expect terminal: complete
### S3 — REVISE then PROCEED
- Inputs: as S1
- Scripted: identify-moments → complete; gate-01 → send_back ("m1 and m2 are duplicates"); identify-moments → complete ([m1, m3]); gate-01 → approve; CMP[m1], CMP[m3] → complete
- Expect visited: [identify-moments, gate-01, identify-moments, gate-01, generate-fragments[m1], generate-fragments[m3], sequence-complete]
- Expect gates: [gate-01: send_back, gate-01: approve]
- Expect terminal: complete
### S4 — REJECT
- Inputs: as S1
- Scripted: identify-moments → complete; gate-01 → reject
- Expect visited: [identify-moments, gate-01]
- Expect gates: [gate-01: reject]
- Expect terminal: rejected (abandoned)
### S5 — Fragment fails DAV once, retried
- Inputs: as S1
- Scripted: gate-01 → approve; CMP[m1] → fail (DAV), CMP[m1] → complete; CMP[m2], CMP[m3] → complete
- Expect visited: [identify-moments, gate-01, generate-fragments[m1], generate-fragments[m1], generate-fragments[m2], generate-fragments[m3], sequence-complete]
- Expect gates: [gate-01: approve]
- Expect terminal: complete (one retry recorded)
### S6 — Empty moment inventory
- Inputs: product/experience/ has no qualifying screens; MOMENTS.md with zero moments
- Scripted: identify-moments → complete (0 moments); gate-01 → approve
- Expect visited: [identify-moments, gate-01, sequence-complete]
- Expect gates: [gate-01: approve]
- Expect terminal: complete (reading: empty for_each yields no fragments)

## Ambiguities for the process owner
- SEQUENCE.yaml says "fan-out" (engine fans out step 2) while DAG says fragments are "generated sequentially"; concurrency is undecided.
- The for-each is expressed only in comments/agent_instructions; neither file declares a for_each node, collection field or item field.
- DAV retry "fix and retry before moving to next moment" has no max attempts and no route when a fragment can never pass (block the run, skip the moment, or escalate).
- REVISE redo budget UNSTATED; "adjusted criteria" has no declared input.
- Gate `decisions` list is a field not in the gate schema (`on_failure: REVISE|REJECT`); PROCEED_WITH_SUBSET needs a selection input with no declared shape.
- Empty MOMENTS.md behaviour (S6) is UNSTATED; gate criteria do not require ≥1 moment.
- Node type `terminal`, node `context`, `outputs`, `agent_instructions` are not in DAG_SCHEMA_SPECIFICATION.
- `--surface` filter is shown in invocation examples but not declared as an input.
- Handoff failure policy UNSTATED (no contract file).
