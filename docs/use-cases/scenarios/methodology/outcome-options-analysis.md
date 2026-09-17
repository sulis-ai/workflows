# options-analysis — methodology outcome

Source: methodology/outcomes/utility/options-analysis/GRAPH.yaml (v2.2.1), methodology/outcomes/utility/options-analysis/OUTCOME.md, methodology/outcomes/utility/options-analysis/lenses/ (option-generator.md, trade-off-analyst.md, constraint-guardian.md)
Purpose: Generate 2–4 distinct options, screen them (FSAD), compare trade-offs and constraints in parallel, recommend one with SCQA framing, get a person's approval and three lens sign-offs, then verify.
Use cases: UC-STATE-CHANNELS, UC-IN-OPTIONAL, UC-MECHANISM, UC-CRITICALITY, UC-PRECONDITION, UC-PARALLEL, UC-JOIN, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-LENS-TRIAD, UC-SPIRAL, UC-LOOP-BUDGET, UC-STOP-NAMED, UC-STOP-HONEST

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| step-01 Define Decision Context | step (process) | Reads upstream *.md; captures question, 3–7 weighted criteria, hard/soft constraints; asks the user if inputs missing | [] / — → decision_context | standard |
| step-02 Option Generation | step (content) | Option Generator lens: 2–4 distinct options (reuse-maximising if IA present) | step-01 / decision_context → options; OPTION_GENERATION.md | standard |
| step-03 Option Screening | step (content) | Constraint Guardian: FSAD pass/fail; <2 survivors is a blocker | step-02 / OPTION_GENERATION.md, decision_context → screened_options; OPTION_SCREENING.md | standard |
| step-04 Trade-off Analysis | step (content) | Trade-off Analyst: weighted matrix, sensitivity, preliminary ranking | step-03 / OPTION_SCREENING.md, decision_context → (writes []) TRADE_OFF_ANALYSIS.md | critical |
| step-05 Constraint Mapping | step (content) | Constraint Guardian: constraint × option matrix, risk register | step-03 / OPTION_SCREENING.md, decision_context → (writes []) CONSTRAINT_MAPPING.md | standard |
| step-06 Generate Recommendation | step (content) | SCQA recommendation, rejected options explained, IA Compliance if IA present | step-04, step-05 / TRADE_OFF_ANALYSIS.md, CONSTRAINT_MAPPING.md, OPTION_SCREENING.md → OPTIONS_ANALYSIS.md | critical |
| gate-01 Options Approval | gate (approval) | Person reviews OPTIONS_ANALYSIS.md against gate-options-approval criteria | step-06 | critical |
| step-07 Lens Sign-Off | step (content) | One section per lens: APPROVED / APPROVED-WITH-RESERVATIONS / REJECTED; any REJECTED blocks verification | gate-01 / OPTIONS_ANALYSIS.md (+ 3 analyses) → LENS_SIGN_OFF.md | standard |
| activity-verify | step (content) | STANDARD_TIER_DEFAULT verification spiral → VERIFICATION_REPORT.md | step-07 / — → VERIFICATION_REPORT.md | critical |

## Routes, gates, loops and contracts as declared
- **Parallel + join:** step-04 and step-05 both depend only on step-03 → static parallel; step-06 depends on both, `join_rule` UNSTATED → schema default `all_success`.
- **Gate:** node `gate-01` (spec_ref `#gate-options-approval`) → `gates.gate-options-approval`: criteria "OPTIONS_ANALYSIS.md exists and is complete", "At least 2 distinct options analyzed", "FSAD screening applied to all options", "Comparison matrix present", "SCQA framing present", "Clear recommendation with rationale"; `approval_required: true`; `on_failure: "REVISE"`. Structural form: approve → step-07; REVISE → send back (Type B: "The human decides where to restart", no graph target, no budget); reject → UNSTATED.
- **Routing nodes, edges, while/for_each:** none.
- **Lens triad:** Option Generator, Trade-off Analyst (lead), Constraint Guardian; single step-07 writes all three sign-offs. Prose: "any rejection must block downstream verification until resolved."
- **Preconditions (OUTCOME.md step specs):** each step `on_failure: blocked` → BLOCKED.md; step 3 POST-02 "At least 2 options pass screening" (resumption "Generate more options or relax constraints"); step 6 PRE-01 "All lens analysis files exist".
- **Conditional content (prose only):** binding conditions OA-BC-01..07 "fire ONLY when IMPLEMENTATION_ASSESSMENT.md is provided"; step-01 "surface explicit questions to the user before proceeding rather than fabricating context".
- **Verification spiral:** tier standard, STANDARD_TIER_DEFAULT; node: ACCA each ≥4, Evidence Grounding ≥4, Structural Coherence ≥4, Honest Uncertainty ≥3; OUTCOME.md custom: Option Distinctness ≥4, Trade-off Specificity ≥4, Recommendation Justification ≥4 (generating_agent); no independence check; max 3; irreducible triggers: <2 distinct options after FSAD, hard constraints eliminate all options, criteria weights contested → escalate to user. Completion needs `Verdict: PASS` on disk.
- **Handoff contracts, optional steps, tail outcomes:** none.

## Scenarios
### S1 — Happy path
- Inputs: BRIEF.md "Choose a queue backend for job dispatch", no IMPLEMENTATION_ASSESSMENT.md
- Scripted: step-01..03 → success (3 options, 3 survive); step-04, step-05 → success; step-06 → success; gate-01 → approve; step-07 → all APPROVED; spiral → pass on pass 1
- Expect visited: [step-01, step-02, step-03, {step-04 | step-05}, step-06, gate-01, step-07, activity-verify]
- Expect gates: [gate-01: approve]
- Expect terminal: complete (Verdict: PASS)

### S2 — Gate sends back once
- Inputs: as S1
- Scripted: gate-01 → send_back (REVISE, note "comparison matrix lacks weights"; person restarts at step-06); step-06 → success; gate-01 → approve; step-07 → all APPROVED; spiral → pass
- Expect visited: [step-01, step-02, step-03, {step-04 | step-05}, step-06, gate-01, step-06, gate-01, step-07, activity-verify]
- Expect gates: [gate-01: send_back, gate-01: approve]
- Expect terminal: complete (Verdict: PASS)

### S3 — Gate rejects
- Inputs: as S1
- Scripted: gate-01 → reject
- Expect visited: [step-01, step-02, step-03, {step-04 | step-05}, step-06, gate-01]
- Expect gates: [gate-01: reject]
- Expect terminal: rejected (best reading; route UNSTATED)

### S4 — Screening leaves one option (honest stop)
- Inputs: decision with a hard constraint that eliminates 2 of 3 options
- Scripted: step-03 → 1 survivor, flagged blocker
- Expect visited: [step-01, step-02, step-03]
- Expect gates: []
- Expect terminal: blocked (BLOCKED.md, "Generate more options or relax constraints")

### S5 — Parallel branch fails, join does not fire
- Inputs: as S1
- Scripted: step-04 → success; step-05 → failed
- Expect visited: [step-01, step-02, step-03, {step-04 | step-05}]
- Expect gates: []
- Expect terminal: blocked (step-06 never ready under all_success)

### S6 — Lens rejects after approval
- Inputs: as S1
- Scripted: gate-01 → approve; step-07 → Constraint Guardian REJECTED
- Expect visited: [step-01, step-02, step-03, {step-04 | step-05}, step-06, gate-01, step-07]
- Expect gates: [gate-01: approve]
- Expect terminal: blocked (verification held "until resolved")

### S7 — Implementation assessment present
- Inputs: BRIEF.md + IMPLEMENTATION_ASSESSMENT.md (queue capability rated FIT)
- Scripted: as S1; step-02 includes a reuse-maximising option; step-06 includes IA Compliance sub-section
- Expect visited: as S1
- Expect gates: [gate-01: approve]
- Expect terminal: complete (Verdict: PASS)

### S8 — Spiral fails once then passes
- Inputs: as S1
- Scripted: as S1; spiral pass 1 → fail (Trade-off Specificity 3); pass 2 → pass
- Expect visited: as S1
- Expect gates: [gate-01: approve]
- Expect terminal: complete (Verdict: PASS)

### S9 — Spiral exhausted / irreducible blocker
- Inputs: as S1, stakeholders dispute criteria weights
- Scripted: as S1; spiral pass 1 → irreducible blocker "criteria weights contested" (variant: passes 1–3 → fail)
- Expect visited: as S1
- Expect gates: [gate-01: approve]
- Expect terminal: escalated (variant: blocked)

## Ambiguities for the process owner
- Send-back target and redo budget for gate-01 are unstated ("the human decides where to restart"); `reject` has no declared route (on_failure only allows REVISE).
- Gate is placed before lens sign-off, but the OUTCOME.md Gate Criteria include "All lenses signed off"; a lens REJECTED after human approval has no route back.
- step-07 REJECTED "must block downstream verification until resolved" — how it is resolved and where it returns is unstated.
- step-06 join rule unstated; a failed step-05 (standard criticality) blocks a critical recommendation under the default.
- Gate linked to its definition only via `spec_ref: "#gate-options-approval"`; node id `gate-01` differs from the gates key.
- Declared state channels `trade_off_data` and `constraint_mapping` (with merge_dicts reducer) are never written; step-04/05 declare `writes: []`. `reads` name files, not state channels (GV-NEW-01).
- File paths disagree: graph writes OPTION_GENERATION.md, OPTION_SCREENING.md, OPTIONS_ANALYSIS.md, LENS_SIGN_OFF.md; OUTCOME.md step specs check lenses/option-generator/ANALYSIS.md, lenses/constraint-guardian/SCREENING.md, synthesis/OPTIONS_ANALYSIS.md, lenses/*/SIGN_OFF.md.
- step-01 asking the user when inputs are missing is an input request in prose with no gate node.
- step-03 prose cites IA-BC-01/02 while the binding conditions table names them OA-BC-01/02.
- Spiral dimensions differ between activity-verify (template defaults) and OUTCOME.md (three custom dimensions); `verification_complete` is never written.
- The `# Gate Definitions` comment sits above activity-verify, suggesting the node was appended in the wrong place (it still parses as a node).
