# product-delivery — methodology studio sequence

Source: methodology/studios/product-development/sequences/product-delivery/SEQUENCE.yaml, methodology/delivery/product/SEQUENCES.md §product-delivery and §YAML Definition, methodology/studios/product-development/STUDIO.yaml (schema meaning: methodology/studios/STUDIO_SCHEMA.md)
Purpose: Take a feature from goal to released, merged code through design, plan, implementation, quality and release logistics, with four approvals.
Use cases: UC-SEQUENCE, UC-CALL, UC-CALL-GATES, UC-EXEC-POLICY, UC-OPTIONAL-BRANCH, UC-ROUTE-EXPR, UC-PARALLEL, UC-JOIN, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-HANDOFF, UC-MECHANISM, UC-SIDE-EFFECT-CLAIM, UC-PRECONDITION, UC-SPIRAL, UC-STOP-NAMED, UC-SEED-ARTIFACTS

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 goal | outcome | PACER goal | — / feature name → goal artifact | UNSTATED |
| 2 project-context | outcome | Existing capabilities, constraints | goal / → EXISTING_CAPABILITIES.md, CONSTRAINTS.md | UNSTATED |
| 3 implementation-assessment (optional) | outcome | Tech fitness for the feature | project-context / → IMPLEMENTATION_ASSESSMENT.md | UNSTATED |
| 4 options-analysis (optional) | outcome | Approach selection | project-context / → OPTIONS_ANALYSIS.md | UNSTATED |
| 5 solution-design | outcome | Working Backwards design | project-context (+ optional 3, 4) / → PR_FAQ.md, USER_GUIDE.md, TEST_SCENARIOS.md, DESIGN.md, IVS.md | UNSTATED |
| 6 cross-function-coordination (optional) | outcome | Cross-function impact | solution-design / → coordination record | UNSTATED |
| 7 stress-testing | outcome | Design Validator + failure modes | solution-design / design set → stress report | UNSTATED |
| GATE 1 — Design Approval | gate (user_approval) | Approve design | stress-testing / design set → decision | UNSTATED |
| 8 production-plan | outcome | Plan and task packages | GATE 1 / DESIGN.md, IVS.md → PLAN.md, TASKS.yaml | UNSTATED |
| 9 production-plan-verification-spiral | outcome (spiral) | Verifies the plan | production-plan / PLAN.md, TASKS.yaml → verification report | UNSTATED |
| GATE 2 — Plan Approval | gate (user_approval) | Approve plan | step 9 / PLAN.md, TASKS.yaml → decision | UNSTATED |
| 10 solution-implementation | outcome | Double-loop TDD build | GATE 2 / TASKS.yaml → code, tests | UNSTATED |
| 11 platform-reconciliation (optional) | outcome | Reconcile manifests with the platform, with user approval | solution-implementation / DESIGN.md §17, manifests → RECONCILIATION_REPORT.md | UNSTATED |
| 12 production-quality | outcome | Strict verification | implementation (or 11) / → VERIFICATION_REPORT.md | UNSTATED |
| GATE 3 — Release Approval | gate (user_approval) | Approve release | production-quality / report → decision | UNSTATED |
| 13 release-logistics | step (sequence-level mechanical activities 1–12; declared as `outcome` in YAML) | Canonicalise specs, registries, checklist, changelog, Completion Validator | GATE 3 / feature artifacts → DOCUMENTATION_CHECKLIST.md, CHANGELOG.md, registry updates | UNSTATED |
| GATE 4 — User Sign-off | gate (user_approval) | Final approval | release-logistics / checklist → decision | UNSTATED |
| branch merge to dev | step (activity 14, after GATE 4; side effect) | Squash-merge feature branch, push | GATE 4 / branch → merged dev | UNSTATED |
| decision-recording | outcome (tail) | ADRs | final gate / → ADR | UNSTATED |
| documentation-sync | outcome (tail) | Doc updates | final gate / → doc updates | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict` ("all outcomes execute in order. Deviation requires explicit approval"), yet steps 3, 4, 6, 11 carry `optional: true`; STUDIO_SCHEMA: "The engine raises an error if an optional flag is set on any step" of a strict sequence.
- Order from `steps` 1…13. SEQUENCES.md chart draws 3 and 4 as sibling branches under project-context (`├─` / `└─`), joined before solution-design; join rule UNSTATED.
- Optional-step conditions:
  - platform-reconciliation: "invoke only when DESIGN.md Section 17 declares platform resources that require deployment"; skip when Section 17 "N/A" or absent.
  - implementation-assessment, options-analysis, cross-function-coordination: condition UNSTATED (cross-function: "No gate blocks for missing output").
- Gates (`gate_after`, `user_approval`; criteria from SEQUENCES.md):
  - GATE 1 after stress-testing: PR_FAQ, USER_GUIDE, TEST_SCENARIOS, DESIGN, IVS complete; Design Validator PASSED; stress report mitigates failure modes.
  - GATE 2 after step 9 (YAML) / after production-plan (SEQUENCES.md): PLAN.md, TASKS.yaml complete; self-contained packages; 100% IVS coverage; no architectural concerns.
  - GATE 3 after production-quality: all categories PASS; Production Guardian APPROVED; tests passing; TASKS.yaml 100% complete.
  - GATE 4 after release logistics: specs canonicalised; docs complete; registry updated; Completion Validator PASSED.
  - Decisions: runtime APPROVED|REJECTED only; send-back and on_failure UNSTATED.
- Release logistics: activities 1–13 run between GATE 3 and GATE 4 ("mechanical … no triad"); activity 12 Completion Validator is an automated check before GATE 4; activity 14 branch merge runs "after GATE 4 approval".
- Tails: `trigger: on_success`, `parallel: true`.
- Handoffs: "embedded in gate criteria"; no contract file; on_failure UNSTATED.
- Spiral: step 9 is a verification-spiral outcome (tier, dimensions, max iterations live in its own GRAPH.yaml). No sequence-level loops.

## Scenarios
### S1 — Minimal required path, all gates approved
- Inputs: feature_name="billing-passthrough"; DESIGN.md §17 = "N/A"
- Scripted: goal, project-context, solution-design, stress-testing → complete; GATE 1 → approve; production-plan → complete; production-plan-verification-spiral → pass; GATE 2 → approve; solution-implementation, production-quality → complete; GATE 3 → approve; release-logistics → complete (Completion Validator pass); GATE 4 → approve; branch merge → complete; tails → complete
- Expect visited: [goal, project-context, solution-design, stress-testing, GATE 1, production-plan, production-plan-verification-spiral, GATE 2, solution-implementation, production-quality, GATE 3, release-logistics, GATE 4, branch-merge, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve, GATE 4: approve]
- Expect terminal: complete

### S2 — All optional steps run
- Inputs: feature_name="compute-controller"; DESIGN.md §17 declares a service; approval given to run 3, 4, 6
- Scripted: as S1 plus implementation-assessment, options-analysis, cross-function-coordination, platform-reconciliation → complete
- Expect visited: [goal, project-context, {implementation-assessment | options-analysis}, solution-design, cross-function-coordination, stress-testing, GATE 1, production-plan, production-plan-verification-spiral, GATE 2, solution-implementation, platform-reconciliation, production-quality, GATE 3, release-logistics, GATE 4, branch-merge, {decision-recording | documentation-sync}]
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve, GATE 4: approve]
- Expect terminal: complete

### S3 — Platform reconciliation skipped by Section 17 condition
- Inputs: feature_name="admin-ui-filter"; DESIGN.md §17 absent
- Scripted: as S1
- Expect visited: as S1 (platform-reconciliation recorded skipped between solution-implementation and production-quality)
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve, GATE 4: approve]
- Expect terminal: complete

### S4 — Rejected at GATE 1
- Inputs: feature_name="billing-passthrough"
- Scripted: goal … stress-testing → complete; GATE 1 → reject
- Expect visited: [goal, project-context, solution-design, stress-testing, GATE 1]
- Expect gates: [GATE 1: reject]
- Expect terminal: rejected (name UNSTATED)

### S5 — Rejected at GATE 2 after a failed plan spiral
- Inputs: feature_name="billing-passthrough"
- Scripted: GATE 1 → approve; production-plan → complete; production-plan-verification-spiral → fail (exhausted inside the outcome); GATE 2 → reject
- Expect visited: [goal, project-context, solution-design, stress-testing, GATE 1, production-plan, production-plan-verification-spiral, GATE 2]
- Expect gates: [GATE 1: approve, GATE 2: reject]
- Expect terminal: rejected (whether a failed spiral outcome reaches GATE 2 at all is unstated)

### S6 — Rejected at GATE 3
- Inputs: feature_name="billing-passthrough"
- Scripted: through production-quality (a category BLOCKED); GATE 3 → reject
- Expect visited: [goal, project-context, solution-design, stress-testing, GATE 1, production-plan, production-plan-verification-spiral, GATE 2, solution-implementation, production-quality, GATE 3]
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: reject]
- Expect terminal: rejected

### S7 — Rejected at GATE 4 (no merge, no tails)
- Inputs: feature_name="billing-passthrough"
- Scripted: through release-logistics; GATE 4 → reject
- Expect visited: [goal, project-context, solution-design, stress-testing, GATE 1, production-plan, production-plan-verification-spiral, GATE 2, solution-implementation, production-quality, GATE 3, release-logistics, GATE 4]
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve, GATE 4: reject]
- Expect terminal: rejected

### S8 — Branch merge claimed once on resume
- Inputs: feature_name="billing-passthrough"
- Scripted: as S1 to GATE 4 approve; branch merge starts, run crashes, run resumes
- Expect visited: [… GATE 4, branch-merge] with one merge side effect recorded
- Expect gates: [GATE 1: approve, GATE 2: approve, GATE 3: approve, GATE 4: approve]
- Expect terminal: complete

## Ambiguities for the process owner
- `type: strict` with `optional: true` steps is an error by STUDIO_SCHEMA; the definition breaks its own schema.
- GATE 2 follows production-plan-verification-spiral in SEQUENCE.yaml but production-plan in SEQUENCES.md (which has no spiral step); step numbering differs (1–13 vs 1–8 with 2a/2b/3a/6a).
- `release-logistics` is declared as an `outcome` but "not governed outcomes with OUTCOME.md" and no such outcome exists; an engine resolving it by slug fails.
- Branch merge (activity 14) after GATE 4 is not a declared step; its relation to tails (before, after, parallel) is unstated.
- Conditions for running implementation-assessment, options-analysis and cross-function-coordination are unstated; whether 3 and 4 run in parallel and their join rule are unstated.
- Section 17 condition is prose, not a state expression.
- No send-back route or budget on any of the four gates; on_failure unstated.
- Whether a failed outcome (e.g. spiral exhausted) stops the run or still reaches its gate is unstated.
- Terminal verdict names and criticality not declared.
