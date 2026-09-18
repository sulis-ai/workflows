# production-plan-verification-spiral — methodology outcome

Source: methodology/outcomes/utility/production-plan-verification-spiral/GRAPH.yaml (v1.2.0), methodology/outcomes/utility/production-plan-verification-spiral/OUTCOME.md
Purpose: Score a production plan (PLAN.md, TASKS.yaml) on eight dimensions, fix what can be fixed autonomously over up to three passes, get an independent score, and write a PASS/BLOCKED report before plan approval.
Use cases: UC-SEED-ARTIFACTS, UC-STATE-CHANNELS, UC-OUT-MULTI, UC-IN-OPTIONAL, UC-MECHANISM, UC-CRITICALITY, UC-PRECONDITION, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-SPIRAL, UC-STOP-NAMED, UC-STOP-HONEST

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| observe | step (process) | Loads PLAN.md, TASKS.yaml, tasks/, MANIFESTS/; halts if PLAN.md or TASKS.yaml absent | [] / — → plan_artifacts | critical |
| orient | step (process) | Loads IVS.md (required), NFR.md, PLATFORM_CONVENTIONS.md, testing.md (optional); halts if IVS.md absent | observe / plan_artifacts → standards | critical |
| decide | step (content) | Scores 8 dimensions 1–5 with evidence; score_status sufficient if all ≥4 | orient (+ loop-back from spiral-route) / plan_artifacts, standards, iteration_count → dimension_scores, score_status; SCORE_CARD.md | critical |
| act | step (process) | Fixes every dimension <4 (dimension 7 only mechanical fixes); increments iteration_count | decide / dimension_scores, plan_artifacts, standards → plan_artifacts, fixes_applied, iteration_count | standard |
| spiral-route | routing | Loop back to decide or exit to independence-check | act / score_status | UNSTATED |
| independence-check | step (process) | Fresh-context sub-agent scores task-completeness and acceptance-criteria-quality; either <3 → BLOCKED | spiral-route / plan_artifacts, dimension_scores, fixes_applied → independence_score | critical |
| report | step (content) | Writes PLAN_VERIFICATION_REPORT.md with `Verdict: PASS` or `Verdict: BLOCKED` | independence-check / dimension_scores, independence_score, fixes_applied, score_status, iteration_count → PLAN_VERIFICATION_REPORT.md | critical |
| activity-verify | step (content) — see ambiguity: declared inside `edges:` | STANDARD_TIER_DEFAULT spiral → VERIFICATION_REPORT.md | report / — → VERIFICATION_REPORT.md | critical |

## Routes, gates, loops and contracts as declared
- **Seeded inputs:** `input_artifacts`: from `production-plan` → PLAN.md, TASKS.yaml, tasks/; from `solution-design` → IVS.md, NFR.md. Schema: missing source files warn, not fail.
- **Routing:** `spiral-route` field `score_status`; routes `sufficient → independence-check`, `gaps_found → decide`; `default: decide`; `max_iterations: 3`; `exit_condition: "score_status == 'sufficient' or iteration_count >= 3"`.
- **Edges with conditions:** observe→orient; orient→decide; decide→act `score_status == 'gaps_found'`; decide→independence-check `score_status == 'sufficient'`; act→spiral-route; spiral-route→decide (loop-back) `score_status == 'gaps_found' and iteration_count < 3`; spiral-route→independence-check `score_status == 'sufficient' or iteration_count >= 3`; independence-check→report.
- **Halts (preconditions):** observe halts with "production-plan-verification-spiral requires PLAN.md and TASKS.yaml … run production-plan first"; orient: "Absent IVS.md is an irreducible blocker — halt if IVS.md is missing"; other standards files noted and skipped.
- **Optional reads:** NFR.md (dimension 6 scores 4 "not applicable" if absent), PLATFORM_CONVENTIONS.md, testing.md.
- **Spiral (the outcome itself):** tier heavy, template HEAVY_TIER_DEFAULT; 8 graph dimensions each ≥4 (task-completeness, implementation-pattern-compliance, acceptance-criteria-quality, test-pyramid-coverage, dev-deployment-verification-phase, nfr-traceability, dependency-graph-integrity, phase-integrity); OUTCOME.md adds ACCA ≥4; independence scorer external_sub_agent on 2 dimensions, block if <3; max 3 iterations; termination reasons sufficient | max_iterations | irreducible_blocker; irreducible triggers: IVS.md absent, PLAN/TASKS absent, genuine dependency cycles, independence <3, NFR constraints with no upstream source.
- **Second spiral (activity-verify):** STANDARD_TIER_DEFAULT, ACCA each ≥4, Evidence Grounding ≥4, Structural Coherence ≥4, Honest Uncertainty ≥3, no independence check, max 3.
- **Completion orders:** file must exist with a Verdict line; "IF BLOCKED: surface the irreducible blockers explicitly; do not mark the outcome complete".
- **Gates:** none in graph. OUTCOME.md "Gate Criteria (GATE 2 — Plan Approval)" belongs to the calling sequence's gate after this outcome.
- **Handoff contracts, optional steps, tail outcomes, triads:** none ("This outcome has no triad").

## Scenarios
Best reading used for visit order: conditional `edges` are authoritative (decide→independence-check when sufficient skips act), and activity-verify is a node after report.

### S1 — Sufficient on first score
- Inputs: PLAN.md, TASKS.yaml (42 tasks), tasks/, IVS.md (18 categories), NFR.md (6 OC-*)
- Scripted: decide → all 8 ≥4 (sufficient); independence-check → 5, 4; report → PASS; activity-verify spiral → pass on pass 1
- Expect visited: [observe, orient, decide, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS; fixes "None — all dimensions met threshold on first pass.")

### S2 — One fix pass then sufficient
- Inputs: as S1, 3 IVS categories unmapped
- Scripted: decide #1 → task-completeness 3 (gaps_found); act → 3 traces added, iteration_count 1; spiral-route → decide; decide #2 → sufficient; independence → 4, 4; report → PASS; activity-verify → pass
- Expect visited: [observe, orient, decide, act, spiral-route, decide, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S3 — Loop exhausted with gaps remaining
- Inputs: as S1, dev deployment phase with weak criteria that fixes do not lift
- Scripted: decide #1–#3 → gaps_found; act ×3 (iteration_count 1, 2, 3); spiral-route #1, #2 → decide; spiral-route #3 → independence-check (iteration_count ≥3); independence → 4, 4; report → BLOCKED (termination reason max_iterations); activity-verify → pass
- Expect visited: [observe, orient, decide, act, spiral-route, decide, act, spiral-route, decide, act, spiral-route, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: blocked (Verdict: BLOCKED, blockers surfaced, outcome not marked complete)

### S4 — Independence check vetoes self-scores
- Inputs: as S1
- Scripted: decide → sufficient; independence-check → acceptance-criteria-quality 2; report → BLOCKED (irreducible blocker with sub-agent evidence)
- Expect visited: [observe, orient, decide, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: blocked (Verdict: BLOCKED)

### S5 — Genuine dependency cycle
- Inputs: TASKS.yaml with cycle T-12→T-19→T-12
- Scripted: decide ×3 → dependency-graph-integrity 2 (gaps_found); act ×3 records potential irreducible blocker, no fix; route exits after iteration 3; independence → 4, 4; report → BLOCKED (irreducible_blocker)
- Expect visited: as S3
- Expect gates: []
- Expect terminal: blocked (Verdict: BLOCKED, termination reason irreducible_blocker)

### S6 — PLAN.md missing
- Inputs: TASKS.yaml, IVS.md only (seed warns on missing PLAN.md)
- Scripted: observe → halt with the declared error
- Expect visited: [observe]
- Expect gates: []
- Expect terminal: blocked ("requires PLAN.md and TASKS.yaml … run production-plan first")

### S7 — IVS.md missing
- Inputs: PLAN.md, TASKS.yaml, tasks/, no IVS.md
- Scripted: observe → ok; orient → halt (irreducible blocker)
- Expect visited: [observe, orient]
- Expect gates: []
- Expect terminal: blocked (IVS.md absent)

### S8 — Optional NFR.md absent
- Inputs: as S1 without NFR.md
- Scripted: orient notes NFR.md absent; decide → nfr-traceability 4 (not applicable), others ≥4; independence → 4, 4; report → PASS; activity-verify → pass
- Expect visited: [observe, orient, decide, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S9 — Final verification spiral exhausted
- Inputs: as S1
- Scripted: as S1 to report → PASS; activity-verify passes 1–3 → fail
- Expect visited: [observe, orient, decide, independence-check, report, activity-verify]
- Expect gates: []
- Expect terminal: blocked (VERIFICATION_REPORT.md not PASS)

## Ambiguities for the process owner
- `activity-verify` is indented under `edges:`, not `nodes:` — as written it is a malformed edge with no from/to and the node does not exist. The scenarios assume it was meant as a node.
- decide→independence-check (edge, when sufficient) contradicts `depends_on`: independence-check depends only on spiral-route, and act depends on decide unconditionally. Under a depends_on reading S1 becomes [observe, orient, decide, act, spiral-route, independence-check, …] with act a no-op that still increments iteration_count.
- spiral-route reads `score_status`, which act never rewrites, so its routes always see the value decide wrote; the `iteration_count >= 3` exit exists only in `exit_condition` and edge text, not in `config.routes`. `default: decide` is a silent loop target if score_status is unset.
- Loop budget counted two ways: router `max_iterations: 3` vs `iteration_count >= 3` incremented by act; unstated whether decide can run a 4th time.
- No early exit on an irreducible blocker: a genuine cycle still burns all three passes.
- Halts in observe/orient are prose ("halt immediately"); no named terminal verdict or BLOCKED artefact is declared for them.
- Verdict threshold for independence: report says PASS needs "all dimensions >= 4 including independence check", while independence-check blocks only below 3; a score of 3 is undefined.
- Tier conflict: the outcome is heavy tier, but activity-verify runs STANDARD_TIER_DEFAULT; OUTCOME.md lists 9 dimensions (adds ACCA), graph scores 8.
- Two reports (PLAN_VERIFICATION_REPORT.md and VERIFICATION_REPORT.md); unstated which verdict decides completion and whether a BLOCKED plan report still runs activity-verify.
- State defaults `""` for dict/list channels; `iteration_count` default is the string "0"; `verification_complete` is never written.
- Seeding says IVS.md comes from solution-design but orient says "from the feature workspace"; which location wins is unstated.
- Dimension 5 evidence says "PHASE-8" in OUTCOME.md but "penultimate phase" / "or equivalent" in the graph.
