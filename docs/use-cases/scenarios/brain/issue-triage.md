# issue-triage — brain

Source: plugins/sulis-brain/instances/issue-triage/workflow.jsonld
Purpose: Reproduce a reported symptom, isolate its root cause, classify it as design flaw, regression or flake, and route it onward without ever building or fixing anything itself.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-IN-AMBIENT, UC-OUT-MULTI, UC-DECIDE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-CALL, UC-CALL-PATH, UC-GATE-HANDOFF, UC-PRECONDITION, UC-CRITICALITY, UC-MECHANISM, UC-CAPABILITY, UC-SIDE-EFFECT-CLAIM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| reproduce | mixed | Attempts to reproduce the symptom; writes `reproduction-ref`, `reproduced` | needs `reproduce`; no tool bound (no tools.jsonld) |
| isolate-root-cause | probabilistic | Names the concrete cause (file/function/config/environment) | needs `isolate-root-cause`; no tool bound |
| classify-outcome | mixed | Classifies into one of three, computes `symptom-fingerprint`, counts prior flake classifications, then routes: design flaw → dispatch; regression → compose requirement + scenario and hand to delivery; flake → audit log | needs `classify-outcome`; prose calls: `decompose-solution` (workflow `dna:workflow:01KWA4JQ5C6TXYJMSKA9Q325S6`) entered at `elicit-forces`; `change-lifecycle` (`dna:workflow:01KX5M1ZDH0D9QZZ1ZC2SM2Y86`) entered at its `deliver` step via `workflows_run` + `workflows_resume` resubmit; `compose_requirement`, `compose_scenario`, `content_put` |

No parallel starts, fan-out or joins are declared: one initial step, every route exclusive. The only non-linear shape is a conditional skip (`reproduce → classify-outcome` when not reproduced); `classify-outcome` is a merge of two exclusive routes.

## Routes as declared
- `reproduce -> isolate-root-cause [if reproduced == true]` → condition `reproduced == true`.
- `reproduce -> classify-outcome [if reproduced == false]` → condition `reproduced == false`.
- `isolate-root-cause -> classify-outcome` → unconditional.
- `classify-outcome -> [terminal:design-flaw-dispatched] [classification == design-flaw-suspected]` → condition `classification == design-flaw-suspected` → terminal verdict `design-flaw-dispatched` (after a call to decompose-solution).
- `classify-outcome -> [terminal:regression-dispatched] [classification == regression-confirmed]` → condition `classification == regression-confirmed` → terminal verdict `regression-dispatched` (after a call to change-lifecycle at deliver).
- `classify-outcome -> [terminal:flake-logged] [classification == flake-or-environment AND recurrence-count + 1 < recurrence-threshold]` → condition on `classification`, `recurrence-count`, `recurrence-threshold` → terminal verdict `flake-logged`.
- `classify-outcome -> [terminal:regression-dispatched] [classification == flake-or-environment AND recurrence-count + 1 >= recurrence-threshold -- MISCLASSIFICATION-REPAIR]` → same keys → terminal verdict `regression-dispatched`. Threshold value: `recurrence-threshold` in state, prose fixes N = 3.

## Scenarios
### S1 — Reproduced design flaw
- Inputs: `symptom-ref = "checkout 500s when cart has >100 items"`, `recurrence-threshold = 3`
- Scripted: reproduce → `reproduced = true`; isolate-root-cause → `root-cause-ref = {file: "cart/limits.py", ...}`; classify-outcome → `design-flaw-suspected`; decompose-solution (from elicit-forces) → dispatched
- Expect visited: [reproduce, isolate-root-cause, classify-outcome, call:decompose-solution→dispatched]
- Expect gates: []
- Expect terminal: design-flaw-dispatched (`dispatch-ref` set)

### S2 — Reproduced regression
- Inputs: `symptom-ref = "test_login fails since commit abc"`
- Scripted: reproduce → true; isolate-root-cause → cause; classify-outcome → `regression-confirmed` (requirement + scenario composed); change-lifecycle (entered at deliver) → dispatched
- Expect visited: [reproduce, isolate-root-cause, classify-outcome, call:change-lifecycle→dispatched]
- Expect gates: []
- Expect terminal: regression-dispatched

### S3 — Flake below threshold
- Inputs: `symptom-ref = "intermittent timeout in CI job 7"`, `recurrence-threshold = 3`
- Scripted: reproduce → true; isolate-root-cause → "shared runner saturation"; classify-outcome → `flake-or-environment`, fingerprint lookup → `recurrence-count = 0`; audit record written
- Expect visited: [reproduce, isolate-root-cause, classify-outcome]
- Expect gates: []
- Expect terminal: flake-logged (`audit-log-ref` set, no dispatch)

### S4 — Flake at threshold, escalated to regression
- Inputs: as S3
- Scripted: classify-outcome → `flake-or-environment`, `recurrence-count = 2` (2 + 1 >= 3); change-lifecycle (at deliver) → dispatched
- Expect visited: [reproduce, isolate-root-cause, classify-outcome, call:change-lifecycle→dispatched]
- Expect gates: []
- Expect terminal: regression-dispatched

### S5 — Not reproduced, logged as flake
- Inputs: `symptom-ref = "operator saw a blank page once"`
- Scripted: reproduce → `reproduced = false`; classify-outcome (no `root-cause-ref`) → `flake-or-environment`, `recurrence-count = 0`
- Expect visited: [reproduce, classify-outcome]
- Expect gates: []
- Expect terminal: flake-logged

### S6 — Not reproduced, recurring, escalated
- Inputs: as S5
- Scripted: reproduce → false; classify-outcome → `flake-or-environment`, `recurrence-count = 5`; change-lifecycle (at deliver) → dispatched
- Expect visited: [reproduce, classify-outcome, call:change-lifecycle→dispatched]
- Expect gates: []
- Expect terminal: regression-dispatched

## Ambiguities for the process owner
- The calls to decompose-solution and change-lifecycle live inside `classify-outcome`'s prose, not as a step bound to a `workflow_dispatch` tool. There is no tools.jsonld at all; every step has `needs` but nothing provides them.
- Whether either call waits for the child's terminal verdict is unstated. The terminal names ("dispatched") suggest start-and-forget, which no use case covers exactly.
- change-lifecycle is entered mid-process at `deliver`, not at its initial step `architect` (via run + resume resubmit). Entering a child at a named step is not a declared capability.
- `recurrence-threshold` is a state key, but prose fixes N = 3. Which wins when they differ?
- `recurrence-count` comes from querying prior runs of this process by fingerprint: a host-provided read that is not declared as ambient input. Whether the current run is persisted before or after the count is unstated.
- `isolate-root-cause` may conclude "no definitive cause is isolable", but `classify-outcome` requires `root-cause-ref` when reproduced. No route for that outcome.
- Which classifications are allowed when `reproduced == false` is unstated (can a non-reproduced symptom be `regression-confirmed`?).
- `classify-outcome` is in `terminal_steps` and also has outgoing routes to terminal verdicts.
- The routes are three steps' worth of work in one step: classify, dispatch, and log. The route conditions are evaluated on outputs of the same step that performs the side effects.
- No failure modes: a failed dispatch, a failed `content_put`, or a failed fingerprint query have no route.
- `final-outcome` duplicates the terminal verdict as a state key; which is authoritative is unstated.
