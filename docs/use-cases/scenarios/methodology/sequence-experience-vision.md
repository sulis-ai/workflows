# experience-vision — methodology sequence

Source: methodology/sequences/experience-vision/DAG.yaml, SEQUENCE.yaml, SEQUENCE.md (skimmed DRAFT_REVISED_JOURNEY.md)
Purpose: Facilitated exploration of an experience vision, turned into reviewable vision documents, then (after an alignment gate) optional prototypes and a vision site.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-SENDBACK, UC-GATE-ROUTE, UC-GATE-CRITERIA, UC-OPTIONAL-BRANCH, UC-PARALLEL, UC-JOIN, UC-FOREACH, UC-CALL, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-LOOP-BUDGET, UC-STOP-NAMED

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| explore | step (agent-facilitation, @explorer, outcome: null) | Divergent conversation; populates Domain 10 (and 1-9) | — / conversation, BUSINESS_CONTEXT.md? → BUSINESS_CONTEXT.md Domain 10, EXPLORATION_JOURNAL.md | UNSTATED (optional: false) |
| gate: Domain 10 approval | gate (approval, iterate) | "User approval of Domain 10 synthesis" | explore | UNSTATED |
| vision-documents | step (document-generation, @explorer, speed 1) | Write vision documents | explore / Domain 10, EXPLORATION_JOURNAL.md, BUSINESS_TYPE.yaml?, ANTI_GOALS.md?, VISION.md? → PERSONAS.md, EXPERIENCE_JOURNEYS.md, SURFACE_MAP.md (+ METRIC_ARCHITECTURE.md, INFORMATION_ARCHITECTURE.md, MARKETING_ARCHITECTURE.md conditional — SEQUENCE.md only) | UNSTATED (optional: false) |
| alignment gate | gate (approval, iterate) | "User alignment — review, comment, evolve until confirmed" | vision-documents | UNSTATED |
| north-star-experience | outcome compliant-mockup-production (artifact_type north_star_experience, speed 2) | Hero-journey HTML prototype | vision-documents (alignment) → north-star HTML; gate "User review of prototype (IR-13)" | UNSTATED (optional: true) |
| surface-prototypes | outcome compliant-mockup-production (per surface) | One prototype per surface in SURFACE_MAP.md | vision-documents (alignment) → per-surface HTML; gate "User review per surface — findings feed back into vision documents" | UNSTATED (optional: true) |
| prototype-assembly | outcome compliant-mockup-production (prototype_set) — SEQUENCE.md/SEQUENCE.yaml only | Link surfaces into prototype/ | surface HTML, PROTOTYPE_MANIFEST.json → prototype/ | UNSTATED (optional) |
| vision-site | outcome vision-site — SEQUENCE.md/SEQUENCE.yaml only | Vision site + promote to product/experience/ | all docs + prototypes → product/experience/; gate "User must approve promotion (HC-2)" | UNSTATED (optional) |

## Routes, gates, loops and contracts as declared
- DAG.yaml (non-standard: top-level `nodes`, no `dag:` wrapper, types agent-facilitation/document-generation/outcome) declares 4 nodes: explore → vision-documents → {north-star-experience, surface-prototypes}. Both prototype nodes depend only on vision-documents → parallel-capable, optional branches; no downstream join node declared.
- SEQUENCE.yaml (`type: guided`) models only steps 3-6: compliant-mockup-production ×3 (north_star, per-surface, prototype_set) and vision-site, all `optional: true`, sequential step numbers. Steps 1-2 are comments ("not modelled here").
- Gates are all per-node `gate:` strings (prose), no criteria lists, no on_failure:
  - explore: "User approval of Domain 10 synthesis"; "User can iterate before approval" → approve / send_back to explore (budget UNSTATED).
  - vision-documents (alignment gate): passes when user confirms "these personas, journeys, hero story, surface boundaries, metrics, and screen organisation accurately represent what we're building"; "Steps 3, 4, and 5 are BLOCKED until the alignment gate passes" → approve / send_back to vision-documents.
  - north-star-experience: "User review of prototype (IR-13)".
  - surface-prototypes: per-surface review; "Findings feed back into PERSONAS.md, EXPERIENCE_JOURNEYS.md, and SURFACE_MAP.md … This is iterative — the two-speed pipeline cycles until the model is solid" → back-edge to vision-documents, no max_iterations (UNSTATED).
  - vision-site: approve promotion to product/experience/ ("No silent promotion").
- Optional branches: "The user may decline" (BC-05) → opt-in flag per optional step.
- For-each: surface-prototypes runs "one clickable HTML prototype per surface defined in SURFACE_MAP.md" → for_each over surfaces; ad_creative/content_page only when MARKETING_ARCHITECTURE.md exists.
- Conditional output: MARKETING_ARCHITECTURE.md "only when a marketing surface exists in SURFACE_MAP.md".
- Optional input: vision-site brief "MAY" be produced by @explorer; if present the outcome skips its self-brief.
- No handoff contract file, no spiral, no triads ("No triad is deployed" for outcome: null steps).

## Scenarios
### S1 — Documents only (all optional prototypes declined)
- Inputs: user conversation available; BUSINESS_CONTEXT.md absent; opt-ins: north_star=false, surfaces=false, assembly=false, vision_site=false
- Scripted: explore → complete; domain-10 gate → approve; vision-documents → complete (no marketing surface); alignment gate → approve
- Expect visited: [explore, domain-10-gate, vision-documents, alignment-gate]
- Expect gates: [domain-10-gate: approve, alignment-gate: approve]
- Expect terminal: complete
### S2 — Full pipeline
- Inputs: opt-ins all true; SURFACE_MAP.md surfaces = [consumer, marketing]
- Scripted: explore → complete; domain-10 gate → approve; vision-documents → complete (incl. MARKETING_ARCHITECTURE.md); alignment gate → approve; north-star-experience → complete, review → approve; surface-prototypes for each [consumer, marketing] → complete, review → approve each; prototype-assembly → complete; vision-site → complete, promotion gate → approve
- Expect visited: [explore, domain-10-gate, vision-documents, alignment-gate, {north-star-experience | surface-prototypes[consumer], surface-prototypes[marketing]}, prototype-assembly, vision-site]
- Expect gates: [domain-10-gate: approve, alignment-gate: approve, north-star-review: approve, surface-review[consumer]: approve, surface-review[marketing]: approve, promotion: approve]
- Expect terminal: complete
### S3 — Domain 10 iterated once
- Inputs: opt-ins all false
- Scripted: explore → complete; domain-10 gate → send_back ("vision misses admin experience"); explore → complete; domain-10 gate → approve; vision-documents → complete; alignment gate → approve
- Expect visited: [explore, domain-10-gate, explore, domain-10-gate, vision-documents, alignment-gate]
- Expect gates: [domain-10-gate: send_back, domain-10-gate: approve, alignment-gate: approve]
- Expect terminal: complete
### S4 — Alignment not reached: prototypes stay blocked
- Inputs: opt-ins north_star=true
- Scripted: explore, domain-10 approve, vision-documents complete; alignment gate → send_back; vision-documents → complete; alignment gate → approve; north-star-experience → complete, review → approve
- Expect visited: [explore, domain-10-gate, vision-documents, alignment-gate, vision-documents, alignment-gate, north-star-experience]
- Expect gates: [domain-10-gate: approve, alignment-gate: send_back, alignment-gate: approve, north-star-review: approve]
- Expect terminal: complete
### S5 — Surface review feeds back into documents (loop taken once)
- Inputs: opt-ins surfaces=true; surfaces=[admin]
- Scripted: through alignment approve; surface-prototypes[admin] → complete; surface review → send_back ("14 nav items: cognitive load"); vision-documents → complete; alignment gate → approve; surface-prototypes[admin] → complete; review → approve
- Expect visited: [explore, domain-10-gate, vision-documents, alignment-gate, surface-prototypes[admin], vision-documents, alignment-gate, surface-prototypes[admin]]
- Expect gates: [domain-10-gate: approve, alignment-gate: approve, surface-review[admin]: send_back, alignment-gate: approve, surface-review[admin]: approve]
- Expect terminal: complete
### S6 — Vision site promotion refused
- Inputs: opt-ins vision_site=true, others false
- Scripted: through alignment approve; vision-site → complete; promotion gate → reject
- Expect visited: [explore, domain-10-gate, vision-documents, alignment-gate, vision-site]
- Expect gates: [domain-10-gate: approve, alignment-gate: approve, promotion: reject]
- Expect terminal: complete without promotion (reading; outputs stay in workspace)

## Ambiguities for the process owner
- DAG.yaml declares 4 nodes; SEQUENCE.yaml declares 4 different steps (3 CMP + vision-site) and omits explore/vision-documents; SEQUENCE.md describes 6 steps. prototype-assembly and vision-site are absent from DAG.yaml.
- SEQUENCE.yaml gives steps 3-6 sequential order; DAG.yaml makes north-star and surface prototypes parallel siblings. Whether prototype-assembly requires surface-prototypes (it needs Step 4 files) and what join rule vision-site uses (optional predecessors) is UNSTATED.
- All gates are prose strings; no criteria lists, no decision vocabulary, no on_failure, no redo budget.
- The surface-review → vision-documents loop ("cycles until the model is solid") has no max_iterations — unbounded as written; whether it re-passes the alignment gate is UNSTATED.
- How an optional step is opted in (flag name, who decides, when asked) is UNSTATED.
- Versions disagree: SEQUENCE.yaml 1.0.0, DAG.yaml 2.0.0, SEQUENCE.md 2.9.0 header vs "v2.8.0" footer.
- @explorer "dispatches outcomes for ready domains" during explore — background calls with no declared list or condition.
- Rejected promotion outcome (S6) terminal is UNSTATED.
- DRAFT_REVISED_JOURNEY.md proposes resequencing (primitive decomposition/testing between vision documents and vision site; vision site "represents TESTED thinking") — disagrees with SEQUENCE.md's step 6 placement; marked DRAFT pending a methodology-change.
