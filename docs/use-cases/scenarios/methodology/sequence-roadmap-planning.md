# roadmap-planning — methodology sequence

Source: methodology/sequences/roadmap-planning/SEQUENCE.yaml, methodology/sequences/roadmap-planning/DAG.yaml, methodology/sequences/roadmap-planning/SEQUENCE.md, methodology/sequences/roadmap-planning/HANDOFF_PROTOCOL.md (schema meaning: methodology/studios/STUDIO_SCHEMA.md, methodology/standards/DAG_SCHEMA_SPECIFICATION.md)
Purpose: Turn project context and a capability map into an approved NOW/NEXT/LATER roadmap, with optional domain-model and technical-fitness steps, then record decisions and sync docs.
Use cases: UC-SEQUENCE, UC-CALL, UC-EXEC-POLICY, UC-OPTIONAL-BRANCH, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-JOIN, UC-PARALLEL, UC-HANDOFF, UC-ROUTE-EXPR, UC-STOP-NAMED, UC-CRITICALITY, UC-SEED-ARTIFACTS, UC-IN-OPTIONAL

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 project-context | outcome | Maps codebase, constraints, ADR catalogue | — / product name → EXISTING_CAPABILITIES.md, CONSTRAINTS.md, CONTEXT_SUMMARY.md | standard |
| 2 product-capability-decomposition | outcome | Builds the capability map | project-context / EXISTING_CAPABILITIES.md, CONSTRAINTS.md → CAPABILITY_MAP.jsonld | standard |
| GATE 1 — Capability Map Approved | gate | Person approves capability map | capability-decomposition / CAPABILITY_MAP.jsonld → decision | critical |
| 3 domain-model-definition (optional) | outcome | Entities, boundaries, relationships | GATE 1 / CAPABILITY_MAP.jsonld → DOMAIN_MODEL.md | UNSTATED (absent from DAG.yaml) |
| GATE 1.5 — Domain Model Approved (optional) | gate | Person approves domain model | domain-model-definition / DOMAIN_MODEL.md → decision | UNSTATED |
| 4 technical-fitness-assessment (optional) | outcome | Rates each capability FIT/ADAPTABLE/GAP/UNFIT | GATE 1 (DAG) or GATE 1.5 (YAML order) / CAPABILITY_MAP.jsonld, DOMAIN_MODEL.md? → TECHNICAL_FITNESS.md | standard |
| GATE 2 — Fitness Assessed (optional) | gate | Person approves fitness ratings | fitness-assessment / TECHNICAL_FITNESS.md → decision | critical |
| 5 product-roadmapping | outcome | Scores and sequences into NOW/NEXT/LATER | DAG: GATE 1 only / CAPABILITY_MAP.jsonld, TECHNICAL_FITNESS.md? → ROADMAP.md | standard |
| GATE 3 — Roadmap Approved | gate | Person approves roadmap | roadmapping / ROADMAP.md → decision | critical |
| decision-recording | outcome (tail) | ADR for decisions | GATE 3 / HANDOFF.md → ADR | standard |
| documentation-sync | outcome (tail) | Updates affected docs | GATE 3 / HANDOFF.md → doc updates | standard |

## Routes, gates, loops and contracts as declared
- Type `guided` → optional steps may be skipped with documented rationale; "Reorder outcomes: No"; "Add outcomes: Yes"; "Repeat outcome: Yes (after obtaining new inputs)".
- SEQUENCE.yaml order: 1 → 2 [GATE 1] → 3 optional [GATE 1.5] → 4 optional [GATE 2] → 5 [GATE 3] → tails. Note: "When step 3 is skipped, its gate is also skipped. When step 4 is skipped, GATE 2 is skipped. Steps must execute in order when present."
- DAG.yaml (v1.1.0, predates DMD): no `default_join_rule` → all_success default. `outcome-fitness-assessment` depends_on [gate-capability-map], `optional: true`; `gate-fitness-assessed` depends_on [outcome-fitness-assessment], `optional: true`; `outcome-roadmapping` depends_on [gate-capability-map] only ("GATE 2 optional"). No edges block, no conditions. Tails `tail: true` depend_on [gate-roadmap-approved] → parallel group.
- Gates (DAG `gates:` block; `approval_required: true`; `on_failure` UNSTATED):
  - gate-capability-map-approved: schema-valid map; every surface covered; every product-affinity primitive has enabling capabilities; dependencies typed, DAG valid; Input Quality Tier recorded.
  - GATE 1.5 (SEQUENCE.md only): entity catalogue covers all surfaces; context boundaries with rationale; ≥2 boundary disputes; relationship diagram; traceability matrix.
  - gate-fitness-assessed: every capability rated; landscape classification; integration risk register (or documented skip); build/buy/adapt recommendations.
  - gate-roadmap-approved: NOW/NEXT/LATER complete; every item scored value AND feasibility; dependency map; every item traces to a strategic bet.
  - Every gate's prose options: PROCEED → approve (next present step); REVISE → send_back, target UNSTATED (best reading: the gated outcome), budget UNSTATED; REJECT → "Abandon sequence".
- Handoffs (HANDOFF_PROTOCOL.md; `on_failure` UNSTATED on all):
  - capability-decomposition → technical-fitness-assessment: CAPABILITY_MAP.jsonld; keys input_quality_tier, capability_count, surface_count, dependency_count; validations: exists and schema-valid, coverage complete, dependencies typed.
  - capability-decomposition → product-roadmapping, `condition: "Step 2 (technical-fitness-assessment) skipped"`: CAPABILITY_MAP.jsonld; keys tfa_skipped=true, tfa_skip_rationale, feasibility_confidence=reduced; validation includes "TFA skip rationale is documented".
  - technical-fitness-assessment → product-roadmapping: TECHNICAL_FITNESS.md; keys fitness_landscape, fit/adaptable/gap/unfit counts, high_risk_pairs; validations: exists, every capability rated, landscape present.
  - product-roadmapping → tail-outcomes: ROADMAP.md; keys now/next/later counts, strategic_bets_covered.
  - No handoff declared into or out of domain-model-definition, nor from project-context.
- Tails: `trigger: on_success`, `parallel: true`. No loops, spirals or triads at sequence level.

## Scenarios
### S1 — Full path, all optional steps run
- Inputs: product_name="sulis-platform"
- Scripted: project-context → complete; capability-decomposition → complete; GATE 1 → approve; domain-model-definition → complete; GATE 1.5 → approve; technical-fitness-assessment → complete; GATE 2 → approve; product-roadmapping → complete; GATE 3 → approve; both tails → complete
- Expect visited: [project-context, product-capability-decomposition, GATE 1, domain-model-definition, GATE 1.5, technical-fitness-assessment, GATE 2, product-roadmapping, GATE 3, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 1.5: approve, GATE 2: approve, GATE 3: approve]
- Expect terminal: complete

### S2 — Both optional steps skipped
- Inputs: product_name="mobile-app-v2", skip=[domain-model-definition, technical-fitness-assessment] with rationale
- Scripted: project-context → complete; capability-decomposition → complete; GATE 1 → approve; product-roadmapping → complete (handoff tfa_skipped=true, feasibility_confidence=reduced); GATE 3 → approve; tails → complete
- Expect visited: [project-context, product-capability-decomposition, GATE 1, product-roadmapping, GATE 3, {decision-recording | documentation-sync}] (DMD, GATE 1.5, TFA, GATE 2 recorded skipped)
- Expect gates: [GATE 1: approve, GATE 3: approve]
- Expect terminal: complete

### S3 — Domain model skipped, fitness assessment run
- Inputs: product_name="sulis-platform", skip=[domain-model-definition]
- Scripted: as S1 without DMD/GATE 1.5
- Expect visited: [project-context, product-capability-decomposition, GATE 1, technical-fitness-assessment, GATE 2, product-roadmapping, GATE 3, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve]
- Expect terminal: complete

### S4 — Fitness skipped, domain model run
- Inputs: product_name="sulis-platform", skip=[technical-fitness-assessment]
- Scripted: GATE 1 approve; DMD complete; GATE 1.5 approve; roadmapping complete (tfa_skipped); GATE 3 approve
- Expect visited: [project-context, product-capability-decomposition, GATE 1, domain-model-definition, GATE 1.5, product-roadmapping, GATE 3, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 1.5: approve, GATE 3: approve]
- Expect terminal: complete

### S5 — GATE 1 sent back once
- Inputs: product_name="sulis-platform", skip both optional
- Scripted: capability-decomposition → complete; GATE 1 → send_back; capability-decomposition → complete; GATE 1 → approve; roadmapping → complete; GATE 3 → approve
- Expect visited: [project-context, product-capability-decomposition, GATE 1, product-capability-decomposition, GATE 1, product-roadmapping, GATE 3, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: send_back, GATE 1: approve, GATE 3: approve]
- Expect terminal: complete

### S6 — GATE 2 sent back once
- Inputs: product_name="sulis-platform", skip=[domain-model-definition]
- Scripted: GATE 1 approve; TFA complete; GATE 2 send_back; TFA complete; GATE 2 approve; roadmapping complete; GATE 3 approve
- Expect visited: [project-context, product-capability-decomposition, GATE 1, technical-fitness-assessment, GATE 2, technical-fitness-assessment, GATE 2, product-roadmapping, GATE 3, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 2: send_back, GATE 2: approve, GATE 3: approve]
- Expect terminal: complete

### S7 — Rejected at GATE 1.5
- Inputs: product_name="sulis-platform"
- Scripted: GATE 1 approve; DMD complete; GATE 1.5 reject
- Expect visited: [project-context, product-capability-decomposition, GATE 1, domain-model-definition, GATE 1.5]
- Expect gates: [GATE 1: approve, GATE 1.5: reject]
- Expect terminal: rejected (name UNSTATED; "Abandon sequence")

### S8 — Rejected at GATE 3 (tails never run)
- Inputs: product_name="sulis-platform", skip both optional
- Scripted: GATE 1 approve; roadmapping complete; GATE 3 reject
- Expect visited: [project-context, product-capability-decomposition, GATE 1, product-roadmapping, GATE 3]
- Expect gates: [GATE 1: approve, GATE 3: reject]
- Expect terminal: rejected

### S9 — Skip-TFA handoff without rationale
- Inputs: product_name="sulis-platform", skip=[domain-model-definition, technical-fitness-assessment] with no rationale
- Scripted: GATE 1 approve; handoff capability-decomposition → product-roadmapping validation "TFA skip rationale is documented" fails (on_failure UNSTATED; best reading block)
- Expect visited: [project-context, product-capability-decomposition, GATE 1]
- Expect gates: [GATE 1: approve]
- Expect terminal: blocked (best reading)

## Ambiguities for the process owner
- DAG.yaml (v1.1.0) has no domain-model-definition node or GATE 1.5; SEQUENCE.yaml and SEQUENCE.md (v1.2.0) do.
- DAG.yaml makes product-roadmapping depend only on GATE 1, so under all_success it becomes ready alongside technical-fitness-assessment (parallel), contradicting "Steps must execute in order" and the TFA → roadmapping handoff. Scenarios follow SEQUENCE.yaml order.
- Whether the optional TFA runs is a person's choice; no state field or condition expresses it except the handoff prose "Step 2 skipped" (which uses the old step number).
- Step numbering disagrees: SEQUENCE.md numbers 0/1/1.5/2/3; SEQUENCE.yaml numbers 1–5.
- REVISE target, revise budget and gate `on_failure` are unstated; runtime accepts only APPROVED|REJECTED.
- No handoff declared for domain-model-definition (in or out) or from project-context; handoff on_failure unstated everywhere.
- GATE 1.5 criteria exist only in prose; criticality of DMD and GATE 1.5 unstated.
- Terminal verdict names are not declared.
- Tail order parallel (SEQUENCE.md) vs "in order" (CREATING_SEQUENCES.md).
