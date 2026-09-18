# change-lifecycle — brain

Source: plugins/sulis-brain/instances/change-lifecycle/workflow.jsonld
Purpose: Take an idea end-to-end from idea to shipped by dispatching existing disciplines (architect → specify → design → deliver → prove, with an opt-in gate → publish).
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-OPTIONAL-BRANCH, UC-CYCLE-POLICY, UC-COMPENSATE, UC-CALL, UC-CALL-NESTING, UC-CALL-GATES, UC-FOREACH, UC-RETRY, UC-FAILURE-MODES, UC-PRECONDITION, UC-CRITICALITY, UC-SIDE-EFFECT-CLAIM, UC-RESUME, UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-TOOL-RUNNER, UC-CAPABILITY, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| architect | deterministic | Design-before-build → `architect-outcome` | dispatch-architect (workflow_dispatch → `architect`, dna:workflow:01KX5KJ0CCM3ABTZFF8QBA5MFP) |
| specify | deterministic | Author opportunity → requirement → scenarios → `specification-refs` | dispatch-specify (workflow_dispatch → `specify`, dna:workflow:01KX5NMPNDWJEEN3NNZ2BGKMAC) |
| design | deterministic | Decompose into work packages, or no-op passthrough for a simple function change → `design-refs` | dispatch-decompose-solution (workflow_dispatch → `decompose-solution` dna:workflow:01KWA4JQ5C6TXYJMSKA9Q325S6, companion `design-work-package` dna:workflow:01KV4B8QK2BKA9ZPBKA3QH7CWW per package; seeds `coverage-repair-count: 0`) |
| deliver | deterministic | Build + reality gate + ship → `delivery-outcome`, `final-outcome` | dispatch-roadmap-loop (workflow_dispatch → `roadmap-loop`, dna:workflow:01KWGQDMA0YGN9ZB2GJAXP1NEZ) |
| prove | deterministic | Drive the change for real and inspect output → `prove-verdict`, `cycle`, `final-outcome` | dispatch-prove (workflow_dispatch → `prove`, dna:workflow:01KX6BH2FE5D1KXEW853JQEM6B) |
| gate | deterministic | WARN-only code-health/security verdict → `gate-verdict` | gate-code-health-verdict (python_import `brain_runtime_runner.generation._verify_code`, query; "NOT YET WIRED") |
| publish | deterministic | Open a real PR, never merge → `publish-outcome` | dispatch-request-review (workflow_dispatch → `request-review`, dna:workflow:01KYS6ATRFR310AJG54AG5QA1K, side-effect) |

## Routes as declared
- `architect -> specify [the dispatched architect Workflow returned final-outcome == architected …]` → condition on child `final-outcome == architected`.
- `architect -> [terminal:blocked] [if the dispatched architect Workflow returned final-outcome == blocked …]` → condition child `final-outcome == blocked` → terminal `blocked`.
- `specify -> design [opportunity -> requirement -> scenario are authored in the brain (via the emit_* Tools) …]` → unconditional (child `specified` assumed); child `blocked` route UNSTATED.
- `design -> deliver [the solution is decomposed into work packages via the dispatched design disciplines, OR the step is a no-op passthrough for a simple function-kind change]` → unconditional; the passthrough decision is inside the step (condition on `architect-outcome.reuse-vs-mint-verdict` "single function", value UNSTATED).
- `deliver -> [terminal:blocked] [the dispatched roadmap-loop blocked -- the change failed the reality gate or had no acceptance criteria; final-outcome == blocked]` → condition child verdict `blocked` → terminal `blocked`.
- `deliver -> prove [the dispatched roadmap-loop delivered the change under its reality gate -- now PROVE it is real, not vibe-coded]` → condition child verdict `shipped`.
- `prove -> [terminal:proven] [every critical scenario driven-green with an inspected saved result AND publish-requested is not set -- final-outcome == proven; …]` → condition `prove-verdict == proven AND NOT publish-requested` → terminal `proven`.
- `prove -> gate [every critical scenario driven-green with an inspected saved result AND publish-requested == true -- an explicit opt-in to additionally open a real PR]` → condition `prove-verdict == proven AND publish-requested == true`.
- `prove -> deliver [META-SPIRAL cycle-back: prove returned prove-verdict == blocked AND should_respiral(prove-verdict, cycle, max-cycles) is true (cycle budget remains) -- … ROTATING the LLM provider for the new cycle via provider_for_cycle(cycle, provider-schedule) … Bounded by max-cycles …]` → loop back to deliver, condition `prove-verdict == blocked AND cycle < max-cycles` (best reading of should_respiral), budget = input `max-cycles`, per-pass policy: provider = provider_for_cycle(cycle, provider-schedule); counter `cycle` incremented.
- `prove -> [terminal:blocked] [prove returned prove-verdict == blocked AND should_respiral is false -- the max-cycles budget is exhausted; …]` → loop exhaustion → terminal `blocked`.
- `gate -> publish [always -- gate is WARN-only and never blocks the lifecycle; …]` → unconditional.
- `publish -> [terminal:published] [the dispatched request-review Workflow reached final-outcome == review-requested -- …]` → condition child `review-requested` → terminal `published`.
- `publish -> [terminal:proven] [precondition short-circuit: no diff existed between the deliver-produced branch and integration-branch -- … final-outcome reverts to proven, NOT an error. dna:failuremode:01KYS6ATRFPFS2SYN6JJ34JHVH]` → precondition failure → terminal `proven` (success).
- `publish -> [terminal:blocked] [request-integration exhausted its bounded retry cap (3 attempts) on a transient failure -- … dna:failuremode:01KYS6ATRFJX9GDK4CEJWFCSTJ]` → retry budget 3 inside the child → terminal `blocked`.

## Scenarios
### S1 — full design, proven, no publish
- Inputs: `subject-ref: dna:idea:csv-export`, `cycle: 0`, `max-cycles: 5`, `provider-schedule: [claude, claude, claude, antigravity, antigravity]`
- Scripted: architect → `architected`; specify → `specified`; design → decompose-solution `decomposed` (2 packages), design-work-package `artifact-produced` ×2; roadmap-loop → `shipped`; prove → `proven`
- Expect visited: [architect[call:architect→architected], specify[call:specify→specified], design[call:decompose-solution→decomposed, call:design-work-package→artifact-produced, call:design-work-package→artifact-produced], deliver[call:roadmap-loop→shipped], prove[call:prove→proven]]
- Expect gates: [] (plus any gates surfacing from children)
- Expect terminal: proven

### S2 — simple function, design passthrough
- Inputs: as S1
- Scripted: architect → `architected` with verdict "single function"; design → passthrough marker (no call); roadmap-loop → `shipped`; prove → `proven`
- Expect visited: [architect[call:architect→architected], specify[call:specify→specified], design, deliver[call:roadmap-loop→shipped], prove[call:prove→proven]]
- Expect gates: []
- Expect terminal: proven

### S3 — architect blocks
- Inputs: as S1
- Scripted: architect → `blocked`
- Expect visited: [architect[call:architect→blocked]]
- Expect gates: []
- Expect terminal: blocked

### S4 — deliver blocks
- Inputs: as S1
- Scripted: roadmap-loop → `blocked`
- Expect visited: [architect[call:architect→architected], specify[call:specify→specified], design[call:decompose-solution→decomposed, call:design-work-package→artifact-produced], deliver[call:roadmap-loop→blocked]]
- Expect gates: []
- Expect terminal: blocked

### S5 — prove fails once, re-spiral with provider rotation, then proven
- Inputs: as S1 (`max-cycles: 5`)
- Scripted: prove pass 1 → `blocked`; should_respiral true, `cycle` 0→1, provider = schedule[1]; roadmap-loop → `shipped`; prove pass 2 → `proven`
- Expect visited: [architect[call:architect→architected], specify[call:specify→specified], design[…], deliver[call:roadmap-loop→shipped], prove[call:prove→blocked], deliver[call:roadmap-loop→shipped], prove[call:prove→proven]]
- Expect gates: []
- Expect terminal: proven

### S6 — prove re-spiral budget exhausted
- Inputs: as S1 but `max-cycles: 2`
- Scripted: every prove → `blocked`; roadmap-loop → `shipped` each pass
- Expect visited: [architect[…], specify[…], design[…], deliver[call:roadmap-loop→shipped], prove[call:prove→blocked], deliver[call:roadmap-loop→shipped], prove[call:prove→blocked], deliver[call:roadmap-loop→shipped], prove[call:prove→blocked]]  (initial pass + 2 re-spirals; exact count depends on should_respiral's comparison, UNSTATED)
- Expect gates: []
- Expect terminal: blocked

### S7 — publish requested, PR opened
- Inputs: as S1 + `publish-requested: true`
- Scripted: prove → `proven`; gate → `{conforms: false, warnings: [...]}` (ignored for routing); request-review → `review-requested`
- Expect visited: [architect[…], specify[…], design[…], deliver[call:roadmap-loop→shipped], prove[call:prove→proven], gate, publish[call:request-review→review-requested]]
- Expect gates: []
- Expect terminal: published

### S8 — publish requested, nothing to publish
- Inputs: as S7
- Scripted: publish precondition finds no diff against integration-branch (no call made)
- Expect visited: [architect[…], specify[…], design[…], deliver[call:roadmap-loop→shipped], prove[call:prove→proven], gate, publish]
- Expect gates: []
- Expect terminal: proven

### S9 — publish requested, PR cannot be opened
- Inputs: as S7
- Scripted: request-review's request-integration fails transiently 3 times
- Expect visited: [architect[…], specify[…], design[…], deliver[call:roadmap-loop→shipped], prove[call:prove→proven], gate, publish[call:request-review→blocked]]
- Expect gates: []
- Expect terminal: blocked

## Ambiguities for the process owner
- Child verdict vocabularies do not match the routes: `specify` can end `blocked` (no route out of specify for it); `roadmap-loop` can end `idle` (no route); `prove` declares only `[terminal:proven]` with a per-scenario observed-or-blocked dict as `prove-verdict`, while this workflow expects `prove-verdict: enum[proven|blocked]`.
- `request-review` declares only `[terminal:review-requested]`; its enum has `no-changes|blocked` with no transitions, so the `publish -> proven` and `publish -> blocked` routes depend on child verdicts the child never routes to.
- The two publish failure modes (01KYS6ATRFPFS2SYN6JJ34JHVH, 01KYS6ATRFJX9GDK4CEJWFCSTJ) are not defined in this instance's failuremodes.jsonld.
- `should_respiral` and `provider_for_cycle` are named engine functions; the comparison (`<` vs `<=`) and who increments `cycle` (prove step writes `cycle`; the prose says the outer driver bumps it) are unstated. The loop is expressed outside the DAG via resume/resubmit.
- On re-spiral, what earlier results are invalidated (the previous `delivery-outcome`, `prove-verdict`) is not declared.
- deliver's postcondition references `final-outcome == shipped -> terminal:shipped`, which is not in the `final-outcome` enum nor a declared terminal.
- The design passthrough condition ("a single simple function") is judgement over `architect-outcome`, with no state value to evaluate. design-work-package "per package" is a for-each with no declared list key, concurrency or merge; which blocked child verdicts stop design is unstated.
- gate's tool is a python_import marked "NOT YET WIRED"; a run would silently no-op or fail.
- `terminal_steps` lists steps `prove`, `gate`, `publish` alongside verdicts; `gate` is never terminal by any route.
- `cycle`, `max-cycles`, `provider-schedule` are required in the state contract but no default or source is declared.
