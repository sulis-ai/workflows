# architect — brain

Source: plugins/sulis-brain/instances/architect/workflow.jsonld
Purpose: Route an idea through the brain before any build by dispatching existing disciplines (gather context, pressure-test, classify reuse-vs-mint, capture the decision, build by dispatch).
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-COMPENSATE, UC-CALL, UC-FOREACH, UC-FAILURE-MODES, UC-PRECONDITION, UC-CRITICALITY, UC-SIDE-EFFECT-CLAIM, UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-CAPABILITY, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| gather-brain-context | deterministic | Assemble the connected brain subgraph for `subject-ref` → `brain-context` | tool gather-brain-context (mcp_server `brain-runtime.graph_gather_context`, query) |
| pressure-test | probabilistic | Pressure-test load-bearing calls → `pressure-test-verdict` (converged/residual/escalated) | tool dispatch-critical-thinking (workflow_dispatch → `critical-thinking`, dna:workflow:01KT1N632VCT1J0XWY7NMVDHCJ, wait) |
| classify-reuse-vs-mint | mixed | Per candidate, classify L1–L4 + routing → `reuse-vs-mint-verdict` | tool dispatch-classify-candidate (workflow_dispatch → `classify-candidate`, dna:workflow:01KX663Q7GRFQK80ZRZZ3DB0FT, wait) |
| capture-decision | deterministic | Capture the load-bearing Decision with alternatives → `decision-ref` | tool emit-decision (subprocess `emit_decision.py`, side-effect) |
| build-by-dispatch | mixed | Route each candidate to its builder (function→roadmap-loop, workflow→discipline-coach, entity→dna-minting-process, reuse→nothing) → `build-dispatch-ref`, `final-outcome` | no tool_ref; `needs: compose-existing-primitives` (resolver UNBUILT) |

## Routes as declared
- `gather-brain-context -> pressure-test [the connected brain subgraph for the subject is assembled]`
  → unconditional sequence (the bracket is a postcondition, not a branch).
- `pressure-test -> classify-reuse-vs-mint [if pressure-test-verdict in (converged, residual) — the load-bearing calls survived the critical-thinking spiral]`
  → condition on `pressure-test-verdict ∈ {converged, residual}`.
- `pressure-test -> gather-brain-context [if the spiral disconfirms on a CONTEXT gap — CYCLE BACK to assemble the missing context, then re-test; invalidates: brain-context (re-assembled); PRESERVED: subject-ref; max_firings: 2 — a second context gap means the subject is under-specified and should block rather than thrash]`
  → loop back to gather-brain-context, budget 2 firings, invalidates `brain-context`. Condition value: UNSTATED (no state key or enum value represents "context gap"). Exhaustion route: UNSTATED (prose says "should block").
- `pressure-test -> [terminal:blocked] [if pressure-test-verdict == escalated — the spiral disconfirmed the PREMISE itself; do not architect against a broken foundation]`
  → condition `pressure-test-verdict == escalated` → terminal verdict `blocked`.
- `classify-reuse-vs-mint -> capture-decision [the reuse-vs-mint verdict (L1/L2/L3/L4 + routing per candidate) exists; default-to-reuse honoured]`
  → unconditional sequence.
- `capture-decision -> build-by-dispatch [the load-bearing Decision is captured WITH alternatives (emit_decision refuses a decision with no options_considered)]`
  → unconditional sequence; refusal route UNSTATED.
- `build-by-dispatch -> [terminal:architected] [each surfaced primitive dispatched into its builder; nothing re-encoded]`
  → terminal verdict `architected` (`final-outcome == architected`).

## Scenarios
### S1 — converged, architected
- Inputs: `subject-ref: dna:idea:demo-001`
- Scripted: gather-brain-context → `brain-context` (non-empty subgraph); critical-thinking → `spiral-converged` (parent records `pressure-test-verdict = converged`); classify-candidate → `classified` (one candidate, L2 propose-convention); emit-decision → `decision-ref: dna:decision:X`; build-by-dispatch → `build-dispatch-ref: []`, `final-outcome = architected`
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→spiral-converged], classify-reuse-vs-mint[call:classify-candidate→classified], capture-decision, build-by-dispatch]
- Expect gates: []
- Expect terminal: architected

### S2 — residual uncertainty still proceeds
- Inputs: `subject-ref: dna:idea:demo-002`
- Scripted: critical-thinking → `spiral-pass-cap-residual` (parent records `residual`); classify-candidate → `classified` (L1 proceed-to-mint); build-by-dispatch dispatches dna-minting-process by judgement
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→spiral-pass-cap-residual], classify-reuse-vs-mint[call:classify-candidate→classified], capture-decision, build-by-dispatch]
- Expect gates: []
- Expect terminal: architected

### S3 — premise disconfirmed, blocked
- Inputs: `subject-ref: dna:idea:broken-premise`
- Scripted: critical-thinking → `scope-misread-escalate` (parent records `escalated`)
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→scope-misread-escalate]]
- Expect gates: []
- Expect terminal: blocked

### S4 — context gap loop taken once
- Inputs: `subject-ref: dna:idea:thin-neighbourhood`
- Scripted: pass 1 critical-thinking → disconfirms on a context gap (verdict value UNSTATED); gather-brain-context re-assembles `brain-context`; pass 2 critical-thinking → `spiral-converged`; rest as S1
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→context-gap], gather-brain-context, pressure-test[call:critical-thinking→spiral-converged], classify-reuse-vs-mint[call:classify-candidate→classified], capture-decision, build-by-dispatch]
- Expect gates: []
- Expect terminal: architected

### S5 — context gap loop exhausted
- Inputs: `subject-ref: dna:idea:under-specified`
- Scripted: critical-thinking → context gap on every pass
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→context-gap], gather-brain-context, pressure-test[call:critical-thinking→context-gap], gather-brain-context, pressure-test[call:critical-thinking→context-gap]]  (best reading of `max_firings: 2`; the prose "a second context gap … should block" would stop one pass earlier)
- Expect gates: []
- Expect terminal: blocked (best reading; no declared exhaustion route)

### S6 — lean child verdict
- Inputs: `subject-ref: dna:idea:small`
- Scripted: critical-thinking → `lean-complete` (best reading: maps to `converged`)
- Expect visited: [gather-brain-context, pressure-test[call:critical-thinking→lean-complete], classify-reuse-vs-mint[call:classify-candidate→classified], capture-decision, build-by-dispatch]
- Expect gates: []
- Expect terminal: architected

### S7 — thin or empty context (failure mode)
- Inputs: `subject-ref: dna:idea:not-in-brain`
- Scripted: gather-brain-context → empty subgraph; failure mode `thin-or-empty-context` fires (recovery escalate, blocks progress)
- Expect visited: [gather-brain-context]
- Expect gates: [operator escalation: seed the subject then re-run gather-brain-context]
- Expect terminal: none — run halted awaiting operator (no terminal verdict declared)

## Ambiguities for the process owner
- The context-gap cycle has no state value: `pressure-test-verdict` is `converged|residual|escalated`, none of which means "context gap", so the route cannot be evaluated from state.
- `max_firings: 2` conflicts with "a second context gap … should block"; the exhaustion route (block) is prose only.
- Verdict vocabulary mismatch: critical-thinking terminates with `lean-complete|spiral-converged|spiral-pass-cap-residual|scope-misread-escalate`, but this step expects `converged|residual|escalated`. The mapping (and where `lean-complete` goes) is not declared.
- `terminal_steps` lists both the step `build-by-dispatch` and the verdicts `[terminal:architected]`/`[terminal:blocked]`.
- classify-reuse-vs-mint says "for each candidate" dispatch classify-candidate, but the tool dispatches once with one `candidate` string; the for-each (and how per-candidate verdicts merge into one dict) is unstated. Where the candidate list comes from is also unstated.
- build-by-dispatch has no tool and dispatches roadmap-loop / discipline-coach / dna-minting-process "by judgement"; the engine cannot express these calls, and their terminal verdicts are not consumed by any route.
- capture-decision: emit_decision refusing a decision (no options_considered) has no failure route.
- `reimplemented-instead-of-dispatched` (abort) and `thin-or-empty-context` (escalate) have no `routes_to`; the resulting run state is unstated. The former is a policy check with no detectable signal in state.
- `final-outcome: enum[architected|blocked]` is only written by build-by-dispatch; the blocked path never writes it.
