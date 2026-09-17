# decompose-solution — brain

Source: plugins/sulis-brain/instances/decompose-solution/workflow.jsonld
Purpose: Frame a requirement set as a problem, synthesise and recursively decompose a solution to leaf Components, verify scenario coverage at every altitude, and hand leaves to build (no `description` on the workflow; purpose taken from the step definitions).
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-SEED-ARTIFACTS, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-STOP-HONEST, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-TERMINATES-WHEN, UC-CALL-DEPTH, UC-FOREACH, UC-CALL, UC-FAILURE-MODES, UC-CRITICALITY, UC-CAPABILITY, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| elicit-forces | mixed | Elicit forces from operator + problem-space → `requirement-set-ref` | needs `elicit-forces` (no tool; resolver) |
| frame-problem | probabilistic | Abstract to one Opportunity; WARN existing-capability check → `opportunity-ref`, `existing-capability-flag` | needs `frame-problem` |
| select-drivers | probabilistic | Mark significance, identify drivers → `drivers-ref` | needs `select-drivers` |
| synthesise-solution | probabilistic | Synthesise a Design for the Opportunity/sub-Design → `design-ref` | needs `synthesise-solution` |
| allocate-forces | mixed | Allocate forces M:N onto the Design; WARN over-coupling → `allocation-ref`, `coupling-warning` | needs `allocate-forces` |
| review-design | probabilistic | Three WARN checks (reuse, smells, workflow-vs-capability) → `design-quality-flag` | needs `review-design` |
| decompose-solution | probabilistic | Emit sub-Designs / leaf Components, derived requirements, depends_on proposal → `decomposition-ref`, `derived-requirements-ref`, `decomposition-depth`, `depends-on-proposal-flag` | needs `decompose-solution` |
| verify-altitudes | mixed | Mint a Scenario per altitude; coverage gate → `scenario-set-ref`, `coverage-verdict` | needs `verify-altitudes` |
| hand-to-build | deterministic | Dispatch the change/build loop per leaf Component → `build-dispatch-ref`, `final-outcome` | needs `hand-to-build` (target workflow not named) |

## Routes as declared
- `elicit-forces -> frame-problem` → unconditional.
- `frame-problem -> select-drivers` → unconditional (existing-capability flag is WARN only).
- `select-drivers -> synthesise-solution [if at least one architecturally-significant requirement (a driver) was identified]` → condition `len(drivers-ref) > 0`.
- `select-drivers -> [terminal:blocked] [if NO driver can be identified]` → condition `len(drivers-ref) == 0` → terminal `blocked` (failure mode no-driver-found).
- `synthesise-solution -> allocate-forces` → unconditional.
- `allocate-forces -> review-design` → unconditional.
- `review-design -> decompose-solution` → unconditional.
- `decompose-solution -> synthesise-solution [CYCLE]` → loop back per non-leaf sub-Design; condition UNSTATED (best reading: decomposition-ref contains a non-leaf sub-Design); budget = depth bound, value UNSTATED; counter `decomposition-depth`.
- `decompose-solution -> verify-altitudes [if every branch bottomed out at leaf Components]` → condition: all branches leaf (measured termination).
- `decompose-solution -> [terminal:blocked] [if decomposition-depth exceeds the bound]` → loop exhaustion → terminal `blocked`; bound UNSTATED.
- `verify-altitudes -> hand-to-build [if the coverage gate PASSES]` → condition `coverage-verdict == covered`.
- `verify-altitudes -> decompose-solution [bounded self-heal]` → loop back; condition UNSTATED (best reading: `coverage-verdict == gap AND gap-kind == missing-solution`); budget = `coverage-repair-count < bound`, bound UNSTATED.
- `verify-altitudes -> verify-altitudes [bounded self-heal]` → self-loop; condition UNSTATED (best reading: `gap-kind == missing-scenario`); same budget, UNSTATED.
- `verify-altitudes -> [terminal:blocked] [if coverage-repair-count >= bound]` → exhaustion → terminal `blocked`; bound UNSTATED.
- `hand-to-build -> [terminal:decomposed]` → terminal `decomposed`.

## Scenarios
### S1 — single altitude, covered
- Inputs: `problem-space: "founders lose track of invoices"`, `decomposition-depth: 0`, `coverage-repair-count: 0`
- Scripted: elicit-forces → 4 requirements; frame-problem → opportunity, no flag; select-drivers → 1 driver; synthesise → design; allocate → allocation; review → no flag; decompose → 3 leaf Components; verify-altitudes → `covered`; hand-to-build → 3 dispatches
- Expect visited: [elicit-forces, frame-problem, select-drivers, synthesise-solution, allocate-forces, review-design, decompose-solution, verify-altitudes, hand-to-build]
- Expect gates: []
- Expect terminal: decomposed

### S2 — no driver
- Inputs: as S1
- Scripted: select-drivers → `drivers-ref: []`
- Expect visited: [elicit-forces, frame-problem, select-drivers]
- Expect gates: []
- Expect terminal: blocked

### S3 — one sub-Design recursion
- Inputs: as S1
- Scripted: decompose pass 1 → 1 sub-Design + 2 leaves, depth 0→1; synthesise/allocate/review on the sub-Design; decompose pass 2 → all leaves
- Expect visited: [elicit-forces, frame-problem, select-drivers, synthesise-solution, allocate-forces, review-design, decompose-solution, synthesise-solution, allocate-forces, review-design, decompose-solution, verify-altitudes, hand-to-build]
- Expect gates: []
- Expect terminal: decomposed

### S4 — decomposition does not terminate
- Inputs: as S1
- Scripted: every decompose pass emits a non-leaf sub-Design until `decomposition-depth` exceeds the bound (say 4)
- Expect visited: [elicit-forces, frame-problem, select-drivers, (synthesise-solution, allocate-forces, review-design, decompose-solution) repeated until the bound]
- Expect gates: []
- Expect terminal: blocked

### S5 — coverage gap repaired by re-decomposing
- Inputs: as S1
- Scripted: verify pass 1 → `gap`, `gap-kind: missing-solution`, repair count 0→1; decompose-solution → all leaves; verify pass 2 → `covered`
- Expect visited: [elicit-forces, frame-problem, select-drivers, synthesise-solution, allocate-forces, review-design, decompose-solution, verify-altitudes, decompose-solution, verify-altitudes, hand-to-build]
- Expect gates: []
- Expect terminal: decomposed

### S6 — coverage gap repaired by minting a scenario
- Inputs: as S1
- Scripted: verify pass 1 → `gap`, `gap-kind: missing-scenario`, count 0→1; verify pass 2 → `covered`
- Expect visited: [elicit-forces, frame-problem, select-drivers, synthesise-solution, allocate-forces, review-design, decompose-solution, verify-altitudes, verify-altitudes, hand-to-build]
- Expect gates: []
- Expect terminal: decomposed

### S7 — coverage repair exhausted
- Inputs: as S1
- Scripted: verify-altitudes → `gap` on every pass until `coverage-repair-count >= bound`
- Expect visited: [elicit-forces, frame-problem, select-drivers, synthesise-solution, allocate-forces, review-design, decompose-solution, verify-altitudes, (verify-altitudes or decompose-solution, verify-altitudes) repeated to the bound]
- Expect gates: []
- Expect terminal: blocked

### S8 — WARN flags ride forward
- Inputs: as S1
- Scripted: frame-problem → `existing-capability-flag: [billing module]`; allocate-forces → `coupling-warning`; review-design → `design-quality-flag: [workflow-vs-capability]`; rest as S1
- Expect visited: as S1
- Expect gates: [] (flags are manual-review, non-blocking)
- Expect terminal: decomposed

## Ambiguities for the process owner
- Neither bound is stated: the decomposition depth bound and the coverage-repair bound. change-lifecycle seeds `coverage-repair-count: 0` but nothing seeds `decomposition-depth`, and no step increments `coverage-repair-count`.
- `decompose-solution -> synthesise-solution [CYCLE]` has no condition, so it overlaps the all-leaf and depth-exceeded routes; the recursion is per sub-Design (a for-each, trigger `subdesign-needs-decomposition`) but is modelled as a single loop edge with no merge of sibling branches.
- The two self-heal edges from verify-altitudes carry identical text; `gap-kind` is in state but not referenced by any route. verify-altitudes' postcondition says `gap -> terminal:blocked`, contradicting the self-heal.
- The coverage-gap failure mode's `routes_to` is a prose sentence ("cycle back to the producing-phase"); `routes_to` is not in the failuremode schema. Several failure modes have null kind/recovery.
- `over-coupling-detected` routes_to `decompose-solution` while allocate-forces' next step is review-design — undeclared edge, or a no-op.
- elicit-forces reads `problem-space`, which is not in the state contract; the trigger allows entering at frame-problem when forces already exist (a second initial step not declared).
- elicit-forces involves the operator (mixed) but no gate kind or decision is declared.
- hand-to-build dispatches "the existing change/build loop" per leaf with no tool or target workflow; its child verdicts are not consumed.
- No step has a tool_ref; every step relies on the unbuilt need→tool resolver. allocate-forces, verify-altitudes and hand-to-build have empty agent_instructions.
- The workflow has `description: null`.
