# author-a-discipline — brain

Source: plugins/sulis-brain/instances/author-discipline/workflow.jsonld
Purpose: Walk the first-principles algorithm to author a discipline (Workflow) for a domain, pressure-test it, and emit it as brain-addressable entities.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-FOREACH, UC-CALL, UC-CALL-DEPTH, UC-GATE-KINDS, UC-FAILURE-MODES, UC-TOOL-RUNNER, UC-CAPABILITY, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| name-outcome | human | Operator names the one outcome entity + domain → `outcome-spec` | — (human input) |
| write-discipline | human | Operator authors ordered steps as NEEDS → `discipline-draft` | — (human input) |
| classify-steps | mixed | Classify each need atomic vs sub-discipline → `step-classifications`, `subdiscipline-queue` | — |
| decompose-subdisciplines | mixed | Recurse: author each queued sub-discipline by re-entering this discipline → updates queue + classifications | — (implicit self-recursion, no tool) |
| defer-mechanism | mixed | Confirm mechanism-free; ensure project context profile exists → `mechanism-deferral-check` | — |
| choose-executor | mixed | Assign agent vs deterministic executor → `executor-assignment` | — |
| pressure-test | probabilistic | Pressure-test the discipline → `pressure-test-trace-ref` | no tool_ref on step; tools.jsonld has dispatch-critical-thinking (workflow_dispatch → `critical-thinking`, name only, no target_workflow_ref) |
| emit-workflow | deterministic | Emit Workflow + Steps as brain entities → `emitted-workflow-ref` | no tool_ref on step; tools.jsonld has emit-workflow-entities (skill_invocation `sulis-brain:build-meta-workflow`) |

## Routes as declared
- `name-outcome -> write-discipline` → unconditional.
- `write-discipline -> classify-steps` → unconditional.
- `classify-steps -> decompose-subdisciplines [if any step is a sub-discipline]` → condition: `subdiscipline-queue` non-empty (best reading).
- `classify-steps -> defer-mechanism [if every step is atomic]` → condition: `subdiscipline-queue` empty (best reading).
- `decompose-subdisciplines -> classify-steps [CYCLE: until the sub-discipline queue is empty]` → loop back while `subdiscipline-queue` non-empty; budget UNSTATED.
- `decompose-subdisciplines -> defer-mechanism [when queue empty]` → condition `subdiscipline-queue` empty.
- `defer-mechanism -> choose-executor` → unconditional.
- `choose-executor -> pressure-test` → unconditional.
- `pressure-test -> emit-workflow [if ooda-verdict == converged]` → condition on `ooda-verdict == converged`; key `ooda-verdict` is not in the state contract (UNSTATED key).
- `pressure-test -> write-discipline [if disconfirms — CYCLE BACK to revise the discipline]` → loop back to write-discipline; condition value UNSTATED; budget UNSTATED.
- (no transition out of emit-workflow) → terminal; verdict name UNSTATED (`final-outcome: enum[authored|revised|aborted]` never routed).
- Failure mode `mechanism-leaked-into-discipline` routes_to `write-discipline`; `context-profile-missing` routes_to `defer-mechanism` → failure routes, budget UNSTATED.

## Scenarios
### S1 — all-atomic discipline, converged
- Inputs: `author-request: {domain: "billing", problem: "reconcile invoices"}`
- Scripted: name-outcome (human input) → `outcome-spec: {entity: Requirement, domain: billing}`; write-discipline (human input) → 4-step draft; classify-steps → all atomic, empty queue; defer-mechanism → profile present; choose-executor → deterministic; pressure-test → call:critical-thinking→spiral-converged (read as `ooda-verdict = converged`); emit-workflow → `emitted-workflow-ref: dna:workflow:X`
- Expect visited: [name-outcome, write-discipline, classify-steps, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome (input), write-discipline (input)]
- Expect terminal: authored (best reading; not declared)

### S2 — one sub-discipline recursed
- Inputs: as S1
- Scripted: classify-steps → one sub-discipline queued; decompose-subdisciplines → recursion authors it (child run of author-a-discipline → authored), queue now empty; classify-steps → all atomic
- Expect visited: [name-outcome, write-discipline, classify-steps, decompose-subdisciplines[call:author-a-discipline→authored], classify-steps, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome, write-discipline, (child) name-outcome, (child) write-discipline, (child) … ]
- Expect terminal: authored

### S3 — sub-discipline queue drains inside decompose
- Inputs: as S1
- Scripted: classify-steps → queue non-empty; decompose-subdisciplines → queue empty afterwards (takes the "when queue empty" route rather than cycling)
- Expect visited: [name-outcome, write-discipline, classify-steps, decompose-subdisciplines[call:author-a-discipline→authored], defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome, write-discipline, child gates]
- Expect terminal: authored

### S4 — pressure-test disconfirms once, revised
- Inputs: as S1
- Scripted: pressure-test pass 1 → disconfirms; write-discipline (human) revises; classify → atomic; … pressure-test pass 2 → converged
- Expect visited: [name-outcome, write-discipline, classify-steps, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→disconfirmed], write-discipline, classify-steps, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome, write-discipline, write-discipline]
- Expect terminal: authored (or `revised` — which applies is UNSTATED)

### S5 — pressure-test never converges
- Inputs: as S1
- Scripted: pressure-test → disconfirms every pass
- Expect visited: [… pressure-test, write-discipline, …] repeating — no budget declared
- Expect gates: [write-discipline on every pass]
- Expect terminal: UNSTATED (best reading: `aborted` when an operator stops; no route exists)

### S6 — context profile missing (failure mode)
- Inputs: as S1
- Scripted: defer-mechanism → `context-profile-missing` fires → routes_to defer-mechanism (after profile is seeded)
- Expect visited: [name-outcome, write-discipline, classify-steps, defer-mechanism, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome, write-discipline]
- Expect terminal: authored

### S7 — mechanism leaked into discipline (failure mode)
- Inputs: as S1
- Scripted: defer-mechanism detects a concrete tool in a step → `mechanism-leaked-into-discipline` → routes_to write-discipline
- Expect visited: [name-outcome, write-discipline, classify-steps, defer-mechanism, write-discipline, classify-steps, defer-mechanism, choose-executor, pressure-test[call:critical-thinking→spiral-converged], emit-workflow]
- Expect gates: [name-outcome, write-discipline, write-discipline]
- Expect terminal: authored

## Ambiguities for the process owner
- `ooda-verdict` is read by the pressure-test routes but is not in the state contract; the step writes `pressure-test-trace-ref` (text). The disconfirm value is unnamed, and critical-thinking's actual verdicts are `lean-complete|spiral-converged|spiral-pass-cap-residual|scope-misread-escalate` — which of those count as converged/disconfirmed is unstated.
- No budget on either cycle (classify↔decompose, pressure-test→write-discipline).
- `final-outcome: enum[authored|revised|aborted]` is never written by any step or routed; no terminal verdict names are declared.
- The two classify-steps routes and the two decompose routes overlap ("any step is a sub-discipline" vs "queue empty"); exhaustiveness relies on reading them as queue empty/non-empty.
- decompose-subdisciplines recurses into this same workflow with no depth limit and no tool (not a declared call).
- Steps carry no `tool_ref`; tools.jsonld tools are unbound. dispatch-critical-thinking has no `target_workflow_ref`; emit-workflow-entities is a skill_invocation of `build-meta-workflow`, which is not a workflow-authoring tool by name.
- Failure modes have `routes_to` (not in the failuremode schema) but no kind, recovery strategy, detection signal or `handles_failures` linkage from a step; which step raises them is unstated.
- No criticality on any step.
