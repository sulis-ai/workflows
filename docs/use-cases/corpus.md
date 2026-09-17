# Golden corpus

Every real process Sulis runs or intends to run, each with scenarios for its declared paths. A process is **supported** by the engine only when every one of its scenarios visits exactly the expected steps, gates and terminal verdict (ADR-227, decision 7).

Scenario files: `scenarios/<source>/<process>.md`. Each lists the process's steps, its routes as declared with the structural form they need, one scenario per declared path, and the **ambiguities** its owner must settle before the scenario is binding.

## Totals

| Processes | Scenarios | Ambiguities for owners | Catalogue ids used |
|---|---|---|---|
| 50 | 415 | 452 | 60 of 63 |

## sulis-brain library (21 processes, 183 scenarios, 192 ambiguities)

| Process | Scenarios | Ambiguities | Use cases |
|---|---|---|---|
| [architect](scenarios/brain/architect.md) | 7 | 9 | CALL, CAPABILITY, COMPENSATE, CRITICALITY, FAILURE-MODES, FOREACH, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TOOL-KINDS, TRIGGER |
| [author-discipline](scenarios/brain/author-discipline.md) | 7 | 8 | CALL, CALL-DEPTH, CAPABILITY, FAILURE-MODES, FOREACH, GATE-KINDS, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, LOOP-WHILE, MECHANISM, OUT-MULTI, ROUTE-DEFAULT, ROUTE-EXPR, STOP-NAMED, TOOL-RUNNER, TRIGGER |
| [change-lifecycle](scenarios/brain/change-lifecycle.md) | 9 | 10 | CALL, CALL-GATES, CALL-NESTING, CAPABILITY, COMPENSATE, CRITICALITY, CYCLE-POLICY, FAILURE-MODES, FOREACH, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OPTIONAL-BRANCH, OUT-MULTI, PRECONDITION, RESUME, RETRY, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TOOL-KINDS, TOOL-RUNNER, TRIGGER |
| [classify-candidate](scenarios/brain/classify-candidate.md) | 5 | 6 | CALL, CRITICALITY, FAILURE-MODES, IN-TYPED, MECHANISM, OUT-TYPED, STOP-NAMED, TRIGGER |
| [compile-manifest](scenarios/brain/compile-manifest.md) | 6 | 7 | CALL, COMPENSATE, CRITICALITY, FAILURE-MODES, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MULTI, OUT-TYPED, ROUTE-DEFAULT, ROUTE-EXPR, STOP-HONEST, STOP-NAMED, TRIGGER |
| [critical-thinking](scenarios/brain/critical-thinking.md) | 15 | 9 | CALL, CALL-PATH, COMPENSATE, CRITICALITY, DECIDE, FAILURE-MODES, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, PATHS, ROUTE-DEFAULT, ROUTE-EXPR, SPIRAL, STOP-HONEST, STOP-NAMED, TOOL-KINDS, TRIGGER |
| [decompose-solution](scenarios/brain/decompose-solution.md) | 8 | 10 | CALL, CALL-DEPTH, CAPABILITY, CRITICALITY, FAILURE-MODES, FOREACH, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, ROUTE-DEFAULT, ROUTE-EXPR, SEED-ARTIFACTS, STOP-HONEST, STOP-NAMED, TERMINATES-WHEN, TRIGGER |
| [design-data-contract](scenarios/brain/design-data-contract.md) | 8 | 6 | CALL, CRITICALITY, FAILURE-MODES, FIDELITY, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MODE, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, STOP-NAMED, TOOL-KINDS, TRIGGER, VERDICT-ROUTE |
| [design-work-package](scenarios/brain/design-work-package.md) | 8 | 7 | CALL, CRITICALITY, FAILURE-MODES, FIDELITY, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MODE, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, STOP-NAMED, TOOL-KINDS, TRIGGER, VERDICT-ROUTE |
| [dna-minting-process](scenarios/brain/dna-minting-process.md) | 17 | 10 | CALL, CALL-NESTING, COMPENSATE, CRITICALITY, DECIDE, FAILURE-MODES, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, RETRY, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-KINDS, TOOL-RUNNER, TRIGGER, VERDICT-ROUTE |
| [faithful-generation-harness](scenarios/brain/faithful-generation-harness.md) | 10 | 8 | CALL, COMPENSATE, CRITICALITY, FAILURE-MODES, FIDELITY, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, REFUSAL-MODE, ROUTE-DEFAULT, ROUTE-EXPR, SPIRAL, STOP-HONEST, STOP-NAMED, TOOL-KINDS, TRIGGER |
| [harness-driver](scenarios/brain/harness-driver.md) | 8 | 14 | CRITICALITY, DECIDE, FAILURE-MODES, FOREACH, IN-AMBIENT, IN-OPTIONAL, IN-TYPED, MECHANISM, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TOOL-KINDS, TOOL-RUNNER, TRIGGER, VERDICT-ROUTE |
| [issue-triage](scenarios/brain/issue-triage.md) | 6 | 11 | CALL, CALL-PATH, CAPABILITY, CRITICALITY, DECIDE, GATE-HANDOFF, IN-AMBIENT, IN-OPTIONAL, IN-TYPED, MECHANISM, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TRIGGER |
| [land-change](scenarios/brain/land-change.md) | 9 | 12 | CALL, CAPABILITY, CRITICALITY, FAILURE-MODES, GATE-ROUTE, IN-AMBIENT, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OPTIONAL-BRANCH, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TRIGGER |
| [ooda-spiral](scenarios/brain/ooda-spiral.md) | 11 | 10 | CALL, CALL-GATES, CALL-NESTING, CRITICALITY, DECIDE, FAILURE-MODES, GATE-KINDS, GATE-ROUTE, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, PATHS, ROUTE-DEFAULT, ROUTE-EXPR, SPIRAL, STATE-CHANNELS, STOP-HONEST, STOP-NAMED, TRIGGER |
| [prove](scenarios/brain/prove.md) | 5 | 8 | CALL, CAPABILITY, CRITICALITY, FAILURE-MODES, FIDELITY, IN-AMBIENT, IN-TYPED, MECHANISM, OUT-TYPED, PRECONDITION, STOP-HONEST, STOP-NAMED, TOOL-EFFECT, TOOL-KINDS, TOOL-RUNNER, TRIGGER |
| [request-review](scenarios/brain/request-review.md) | 5 | 8 | CALL, CAPABILITY, CRITICALITY, FAILURE-MODES, IN-AMBIENT, IN-TYPED, MECHANISM, OPTIONAL-BRANCH, PRECONDITION, RETRY, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TOOL-RUNNER |
| [research-synthesis](scenarios/brain/research-synthesis.md) | 13 | 11 | CALL, CALL-GATES, CALL-NESTING, COMPENSATE, DECIDE, FAILURE-MODES, FOREACH, GATE-KINDS, GATE-ROUTE, IN-OPTIONAL, IN-TYPED, JOIN, LENS-TRIAD, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, ROUTE-DEFAULT, ROUTE-EXPR, SPIRAL, STOP-HONEST, STOP-NAMED, TRIGGER, VERDICT-ROUTE |
| [roadmap-loop](scenarios/brain/roadmap-loop.md) | 10 | 10 | CALL, DECIDE, FAILURE-MODES, IN-AMBIENT, IN-TYPED, MECHANISM, OPTIONAL-BRANCH, OUT-MULTI, PATHS, RETRY, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-HONEST, STOP-NAMED, TOOL-EFFECT, TOOL-RUNNER, TRIGGER, VERDICT-ROUTE |
| [specify](scenarios/brain/specify.md) | 7 | 8 | CALL, CAPABILITY, CRITICALITY, FAILURE-MODES, FOREACH, IN-AMBIENT, IN-TYPED, MECHANISM, OUT-TYPED, PRECONDITION, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-EFFECT, TOOL-KINDS, TRIGGER, VERDICT-ROUTE |
| [sync-narrative-docs](scenarios/brain/sync-narrative-docs.md) | 9 | 10 | FAILURE-MODES, GATE-KINDS, GATE-ROUTE, IN-AMBIENT, IN-TYPED, LOOP-BUDGET, MECHANISM, OPTIONAL-BRANCH, PRECONDITION, RETRY, ROUTE-DEFAULT, ROUTE-EXPR, SIDE-EFFECT-CLAIM, STOP-NAMED, TOOL-RUNNER, TRIGGER |

## fd-product-architecture (6 processes, 57 scenarios, 54 ambiguities)

| Process | Scenarios | Ambiguities | Use cases |
|---|---|---|---|
| [author-tool](scenarios/fd/author-tool.md) | 4 | 6 | IN-TYPED, MECHANISM, OUT-MULTI, OUT-TYPED, ROUTE-DEFAULT, ROUTE-EXPR, STOP-NAMED, TOOL-KINDS, TOOL-RUNNER |
| [change-verification-gate](scenarios/fd/change-verification-gate.md) | 6 | 6 | FAILURE-MODES, IN-AMBIENT, IN-OPTIONAL, IN-TYPED, MECHANISM, PRECONDITION, STATE-CHANNELS, STOP-NAMED, TOOL-KINDS |
| [conformance-convergence](scenarios/fd/conformance-convergence.md) | 10 | 9 | CALL, DECIDE, FOREACH, IN-AMBIENT, IN-TYPED, LOOP-BUDGET, OUT-MULTI, PATHS, PRECONDITION, ROUTE-DEFAULT, STATE-CHANNELS, STOP-NAMED, TERMINATES-WHEN, TOOL-KINDS |
| [grounded-inquiry](scenarios/fd/grounded-inquiry.md) | 15 | 12 | APPROVAL-AUTO, CALL, CALL-DEPTH, CALL-GATES, DECIDE, FIDELITY, FOREACH, GATE-AUDIT, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, IN-AMBIENT, IN-FALLBACK, IN-TYPED, JOIN, LOOP-BUDGET, LOOP-MANY, OUT-MULTI, OUT-TYPED, PATHS, PRECONDITION, PREPHASE, REFUSAL-MODE, ROUTE-DEFAULT, STATE-CHANNELS, STOP-HONEST, STOP-NAMED, TERMINATES-WHEN, VERDICT-ROUTE |
| [recursive-refinement](scenarios/fd/recursive-refinement.md) | 12 | 11 | CALL, CALL-DEPTH, CALL-GATES, CALL-NESTING, CALL-PATH, DECIDE, FOREACH, IN-AMBIENT, IN-FALLBACK, IN-TYPED, LOOP-BUDGET, PATHS, PRECONDITION, ROUTE-DEFAULT, STATE-CHANNELS, STOP-HONEST, STOP-NAMED, TERMINATES-WHEN |
| [solution-delivery](scenarios/fd/solution-delivery.md) | 10 | 10 | APPROVAL-AUTO, CALL, CALL-GATES, CALL-PATH, GATE-AUDIT, GATE-CRITERIA, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-AMBIENT, IN-FALLBACK, IN-TYPED, LOOP-BUDGET, OUT-TYPED, PRECONDITION, REFUSAL-MODE, STOP-HONEST, STOP-NAMED, VERDICT-ROUTE |

## platform methodology (19 processes, 149 scenarios, 183 ambiguities)

| Process | Scenarios | Ambiguities | Use cases |
|---|---|---|---|
| [outcome-options-analysis](scenarios/methodology/outcome-options-analysis.md) | 9 | 11 | CRITICALITY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-OPTIONAL, JOIN, LENS-TRIAD, LOOP-BUDGET, MECHANISM, PARALLEL, PRECONDITION, SPIRAL, STATE-CHANNELS, STOP-HONEST, STOP-NAMED |
| [outcome-production-plan-verification-spiral](scenarios/methodology/outcome-production-plan-verification-spiral.md) | 9 | 12 | CRITICALITY, IN-OPTIONAL, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SEED-ARTIFACTS, SPIRAL, STATE-CHANNELS, STOP-HONEST, STOP-NAMED |
| [outcome-research-synthesis](scenarios/methodology/outcome-research-synthesis.md) | 9 | 15 | CRITICALITY, JOIN, LENS-TRIAD, LOOP-BUDGET, LOOP-MANY, MECHANISM, OUT-MULTI, PARALLEL, PRECONDITION, ROUTE-DEFAULT, ROUTE-EXPR, SEED-ARTIFACTS, SPIRAL, STATE-CHANNELS, STOP-HONEST, STOP-NAMED, VERDICT-ROUTE |
| [sequence-architecture-evolution](scenarios/methodology/sequence-architecture-evolution.md) | 7 | 11 | EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, JOIN, MECHANISM, OUT-TYPED, PARALLEL, SEED-ARTIFACTS, SEQUENCE, STOP-NAMED |
| [sequence-blueprint-extraction](scenarios/methodology/sequence-blueprint-extraction.md) | 7 | 10 | CALL, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, IN-TYPED, OUT-MULTI, REFUSAL-MODE, SEQUENCE, STOP-HONEST, STOP-NAMED |
| [sequence-codebase-restructure](scenarios/methodology/sequence-codebase-restructure.md) | 6 | 9 | CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, HANDOFF, JOIN, OUT-TYPED, PARALLEL, RETRY, SEQUENCE, SIDE-EFFECT-CLAIM, STOP-NAMED |
| [sequence-experience-vision](scenarios/methodology/sequence-experience-vision.md) | 6 | 9 | CALL, EXEC-POLICY, FOREACH, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, IN-OPTIONAL, JOIN, LOOP-BUDGET, MECHANISM, OPTIONAL-BRANCH, OUT-MULTI, PARALLEL, SEQUENCE, STOP-NAMED |
| [sequence-fragment-generation](scenarios/methodology/sequence-fragment-generation.md) | 6 | 9 | CALL, CRITICALITY, EXEC-POLICY, FOREACH, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-TYPED, RETRY, SEQUENCE, STOP-NAMED |
| [sequence-methodology-change](scenarios/methodology/sequence-methodology-change.md) | 13 | 12 | CRITICALITY, DECIDE, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, JOIN, OUT-MULTI, PARALLEL, PATHS, PRECONDITION, PREPHASE, ROUTE-DEFAULT, ROUTE-EXPR, SEQUENCE, STOP-NAMED |
| [sequence-new-feature](scenarios/methodology/sequence-new-feature.md) | 11 | 12 | CALL, CALL-GATES, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, IN-OPTIONAL, JOIN, OUT-MULTI, PARALLEL, SEQUENCE, STOP-NAMED, VERSION |
| [sequence-new-journey](scenarios/methodology/sequence-new-journey.md) | 9 | 11 | CALL-GATES, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, IN-OPTIONAL, JOIN, OUT-MULTI, PARALLEL, SEQUENCE, STOP-NAMED, VERSION |
| [sequence-new-outcome](scenarios/methodology/sequence-new-outcome.md) | 12 | 12 | COMPENSATE, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, JOIN, LOOP-BUDGET, OUT-MULTI, PARALLEL, PRECONDITION, RESUME, SEQUENCE, STOP-NAMED, VERDICT-ROUTE |
| [sequence-research](scenarios/methodology/sequence-research.md) | 7 | 7 | CALL, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, JOIN, OPTIONAL-BRANCH, PARALLEL, SEED-ARTIFACTS, SEQUENCE, STOP-NAMED |
| [sequence-roadmap-planning](scenarios/methodology/sequence-roadmap-planning.md) | 9 | 9 | CALL, CRITICALITY, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, IN-OPTIONAL, JOIN, OPTIONAL-BRANCH, PARALLEL, ROUTE-EXPR, SEED-ARTIFACTS, SEQUENCE, STOP-NAMED |
| [sequence-studio-creation](scenarios/methodology/sequence-studio-creation.md) | 6 | 7 | CALL, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, HANDOFF, LENS-TRIAD, MECHANISM, OPTIONAL-BRANCH, PARALLEL, PATHS, SEQUENCE, STOP-NAMED, TOOL-RUNNER |
| [studio-sequence-journey-lifecycle](scenarios/methodology/studio-sequence-journey-lifecycle.md) | 5 | 6 | CALL, CALL-GATES, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, HANDOFF, PARALLEL, SEQUENCE, STOP-NAMED |
| [studio-sequence-product-delivery](scenarios/methodology/studio-sequence-product-delivery.md) | 8 | 9 | CALL, CALL-GATES, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, HANDOFF, JOIN, MECHANISM, OPTIONAL-BRANCH, PARALLEL, PRECONDITION, ROUTE-EXPR, SEED-ARTIFACTS, SEQUENCE, SIDE-EFFECT-CLAIM, SPIRAL, STOP-NAMED |
| [studio-sequence-product-evolve](scenarios/methodology/studio-sequence-product-evolve.md) | 7 | 8 | CALL, DECIDE, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-HANDOFF, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, HANDOFF, OUT-MULTI, PATHS, ROUTE-DEFAULT, ROUTE-EXPR, SEQUENCE, STOP-NAMED |
| [studio-sequence-quick-feature](scenarios/methodology/studio-sequence-quick-feature.md) | 3 | 4 | CALL, EXEC-POLICY, GATE-AUDIT, GATE-CRITERIA, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, SEQUENCE, STOP-NAMED |

## platform content service (4 processes, 26 scenarios, 23 ambiguities)

| Process | Scenarios | Ambiguities | Use cases |
|---|---|---|---|
| [content-generation](scenarios/content/content-generation.md) | 8 | 7 | GATE-AUDIT, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MODE, RESUME, RETRY, STOP-NAMED |
| [instruction-decomposition](scenarios/content/instruction-decomposition.md) | 5 | 5 | FOREACH, GATE-AUDIT, GATE-HANDOFF, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MODE, OUT-TYPED, RETRY, STOP-NAMED |
| [instruction-generation](scenarios/content/instruction-generation.md) | 7 | 6 | GATE-AUDIT, GATE-HANDOFF, GATE-KINDS, GATE-ROUTE, GATE-SENDBACK, GATE-VOCAB, IN-OPTIONAL, IN-TYPED, LOOP-BUDGET, MECHANISM, OUT-MODE, OUT-TYPED, RESUME, RETRY, STOP-NAMED |
| [outcome-review](scenarios/content/outcome-review.md) | 6 | 5 | GATE-AUDIT, GATE-HANDOFF, GATE-KINDS, GATE-ROUTE, GATE-VOCAB, IN-TYPED, MECHANISM, OUT-MODE, OUT-TYPED, RESUME, RETRY, STOP-NAMED |

## How often each need appears

Processes needing each catalogue id. An id no corpus process needs yet is kept because the engine plan requires it (`UC-OUT-REPAIR`, `UC-LEASE`) or a later process will.

| Use case | Processes |
|---|---|
| UC-STOP-NAMED | 50 |
| UC-CALL | 34 |
| UC-MECHANISM | 34 |
| UC-IN-TYPED | 33 |
| UC-CRITICALITY | 29 |
| UC-GATE-ROUTE | 28 |
| UC-GATE-KINDS | 27 |
| UC-OUT-MULTI | 27 |
| UC-LOOP-BUDGET | 26 |
| UC-ROUTE-DEFAULT | 25 |
| UC-ROUTE-EXPR | 25 |
| UC-IN-OPTIONAL | 24 |
| UC-GATE-AUDIT | 23 |
| UC-GATE-VOCAB | 23 |
| UC-PRECONDITION | 22 |
| UC-FAILURE-MODES | 21 |
| UC-TRIGGER | 20 |
| UC-GATE-CRITERIA | 19 |
| UC-GATE-SENDBACK | 17 |
| UC-EXEC-POLICY | 16 |
| UC-SEQUENCE | 16 |
| UC-STOP-HONEST | 15 |
| UC-JOIN | 14 |
| UC-PARALLEL | 14 |
| UC-FOREACH | 13 |
| UC-HANDOFF | 13 |
| UC-IN-AMBIENT | 13 |
| UC-TOOL-KINDS | 13 |
| UC-DECIDE | 12 |
| UC-OUT-TYPED | 12 |
| UC-SIDE-EFFECT-CLAIM | 12 |
| UC-RETRY | 11 |
| UC-VERDICT-ROUTE | 11 |
| UC-CALL-GATES | 10 |
| UC-LOOP-MANY | 10 |
| UC-OPTIONAL-BRANCH | 10 |
| UC-TOOL-RUNNER | 10 |
| UC-CAPABILITY | 9 |
| UC-PATHS | 9 |
| UC-COMPENSATE | 8 |
| UC-SPIRAL | 8 |
| UC-STATE-CHANNELS | 8 |
| UC-TOOL-EFFECT | 8 |
| UC-SEED-ARTIFACTS | 7 |
| UC-OUT-MODE | 6 |
| UC-CALL-NESTING | 5 |
| UC-FIDELITY | 5 |
| UC-GATE-HANDOFF | 5 |
| UC-RESUME | 5 |
| UC-CALL-DEPTH | 4 |
| UC-CALL-PATH | 4 |
| UC-LENS-TRIAD | 4 |
| UC-REFUSAL-MODE | 4 |
| UC-TERMINATES-WHEN | 4 |
| UC-IN-FALLBACK | 3 |
| UC-APPROVAL-AUTO | 2 |
| UC-PREPHASE | 2 |
| UC-VERSION | 2 |
| UC-CYCLE-POLICY | 1 |
| UC-LOOP-WHILE | 1 |
| UC-CALL-RESULT | 0 |
| UC-LEASE | 0 |
| UC-OUT-REPAIR | 0 |

## What the corpus shows

These hold across sources and shape the `v1` format more than any single process does.

1. **Every process needs named endings, and most need calls.** All 50 end with a named verdict; 34 call another process. Calls are made four different ways in brain alone (dispatch tool, skill, judgement, self-recursion).
2. **Parents and children disagree about results.** critical-thinking's verdicts do not match what architect, author-a-discipline or dna-mint route on; prove and request-review never produce the verdicts change-lifecycle expects; grounded-inquiry's call to conformance-convergence is never made and has no input mapping. → `UC-CALL-RESULT` (added to the catalogue from this finding).
3. **Loops rarely state a budget.** 26 processes loop; most loops outside the fd executor and the content service have no maximum, and no methodology send-back names a destination or a redo limit. → budgets are mandatory in `v1`.
4. **Conditions are judgements, not state.** Many brain and methodology routes test things no step writes ("context gap", "repairable", `ooda-verdict` in author-a-discipline) or undeclared inputs. → every condition reads declared state; the validator refuses the rest.
5. **Routes hide in failure-mode prose.** roadmap-loop, specify, ooda-spiral (four loop-backs), research-synthesis and land-change route differently in failure modes than in transitions; `routes_to` is not in the brain schema. → failure handling is routes, in one place.
6. **Decision words differ everywhere.** PERMIT/DENY/INDETERMINATE, APPROVED/REJECTED, REVISE/REJECT, APPROVE/REVISE/ABANDON, proceed/revise/reject, and a "reject" that means send back. → one vocabulary with a mapping table.
7. **The same process has conflicting definitions.** Methodology SEQUENCE.yaml, DAG.yaml and SEQUENCE.md list different steps (experience-vision: 4, a different 4, and 6); node types `terminal`, `router`, `checkpoint`, `tail`, `loop` are undefined; product-delivery names a missing outcome. → one definition per process, and conversion must pick one with the owner.
8. **Declared intent and executed behaviour diverge in fd.** Halt vs pause, preconditions (including before a destructive step), `terminates_when`, and routes and limits that exist only in Python. Nested runs auto-approve, so child gates never reach a person. → `UC-REFUSAL-MODE`, `UC-PRECONDITION`, `UC-CALL-GATES` are conformance cases, not documentation.
9. **Parallel work is rarer than it looks.** Only research-synthesis (one call per contradiction) and grounded-inquiry (one inquiry per sub-brief) truly fan out, and neither declares concurrency, a join or how verdicts combine. → `for_each` with explicit join and merge; parallel stays in the format but is not the first increment.
10. **Handoffs live in host code.** The content service's send-back to a new instruction, decomposition, and one child instruction per piece are Python in the agents service. → handoffs are routes to a process (`UC-GATE-HANDOFF`).

## Using the ambiguities

Each scenario file's ambiguities are questions for that process's owner. Conversion (plan A6) turns each answer into structure. A scenario whose expected result depends on an unsettled ambiguity is marked *provisional* and does not count toward "supported" until settled.
