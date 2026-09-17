# ooda-spiral — brain

Source: plugins/sulis-brain/instances/ooda-spiral/workflow.jsonld
Purpose: Route an analytical request through a complexity gate, then either answer in a single lean pass or run Observe → Orient → Decide → Act → Self-attack passes until the conclusion survives attack or a 4-pass cap is reached with residual uncertainty stated.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-STATE-CHANNELS, UC-DECIDE, UC-PATHS, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-SPIRAL, UC-STOP-NAMED, UC-STOP-HONEST, UC-FAILURE-MODES, UC-GATE-KINDS, UC-GATE-ROUTE, UC-CALL, UC-CALL-GATES, UC-CALL-NESTING, UC-CRITICALITY, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| complexity-gate | deterministic | Classifies the request lean or spiral (four-row table; ambiguous → spiral; forced spiral when dispatched by critical-thinking) → `complexity-verdict` | none |
| observe | mixed | Gathers evidence and counter-evidence, base rate, source tiers; on a later pass starts from the self-attack's line of attack → `evidence-set` | none (web search / fetch in prose) |
| orient | mixed | MECE decomposition, primitive grounding, assumptions tagged load-bearing/incidental → `decomposition` | none |
| decide | probabilistic | Candidate conclusion with per-claim confidence, basis, falsification condition → `candidate-conclusion` | none |
| act | deterministic | Records the candidate conclusion verbatim as the pass-N conclusion → `applied-record` | none |
| self-attack | probabilistic | Strongest counter-argument, predicted disconfirming evidence, search, `material_disconfirmation` → `self-attack-result` | none |
| converge-or-pass-cap | mixed | Four-condition convergence test, pass counting, cycle routing, anti-thrash guard → `final-verdict`, `spiral-trace`, `residual-uncertainty?`, `material-disconfirmation`, `pass-count`, `convergence-criteria-met` | none |

No parallel starts, fan-out or joins are declared inside this process. Fan-out happens in a caller: research-synthesis's `surface-contradictions` may dispatch this process N times (one child run per divergence point). `decide` and `converge-or-pass-cap` are merge points of exclusive routes (lean/spiral), not joins.

## Routes as declared
- `complexity-gate -> observe [if complexity-verdict == spiral]` → condition `complexity-verdict == spiral`.
- `complexity-gate -> decide [if complexity-verdict == lean — single-pass shortcut: skip orient + self-attack]` → condition `complexity-verdict == lean`.
- `observe -> orient` → unconditional.
- `orient -> decide` → unconditional.
- `decide -> act` → unconditional.
- `act -> self-attack [if complexity-verdict == spiral]` → condition `complexity-verdict == spiral`.
- `act -> converge-or-pass-cap [if complexity-verdict == lean — terminal:lean-complete via the converge gate]` → condition `complexity-verdict == lean`.
- `self-attack -> converge-or-pass-cap` → unconditional.
- `converge-or-pass-cap -> observe [if material-disconfirmation AND pass-count < 4 — CYCLE: the canonical OODA loop; new pass starts with the self-attack's line of attack as evidence to gather]` → loop on `material-disconfirmation == true`, budget `pass-count < 4` (max 4 passes); exhaustion → the pass-cap terminal below.
- `converge-or-pass-cap -> [terminal:converged] [if convergence-criteria-met AND NOT material-disconfirmation]` → condition on `convergence-criteria-met`, `material-disconfirmation` → terminal verdict `converged`.
- `converge-or-pass-cap -> [terminal:pass-cap-residual-uncertainty] [if pass-count >= 4 AND NOT convergence-criteria-met]` → condition on `pass-count`, `convergence-criteria-met` → terminal verdict `pass-cap-residual-uncertainty` (an honest stop).
- `converge-or-pass-cap -> [terminal:lean-complete] [if complexity-verdict == lean]` → condition `complexity-verdict == lean` → terminal verdict `lean-complete`. The step's instructions evaluate this first.
- Routes stated only in failure modes (not in transitions):
  - rebuttal-unexamined (compensate) → back to `self-attack` with the rebuttal as target; counts toward the pass cap.
  - convergence-faked (manual-review) → person decides: genuine → converge route; theatre → back to `self-attack` with must-attack targets; autonomous mode → "manual-review terminal".
  - complexity-misclassified (compensate) → after lean `decide`, flip `complexity-verdict := spiral` and go to `observe`; lean pass counts as pass 1.
  - anti-thrash guard (step instructions) → two passes revising the same load-bearing assumption back and forth → pass-cap terminal before pass 4.

## Scenarios
### S1 — Lean single pass
- Inputs: `request = {text: "poke holes in: our churn is seasonal"}`
- Scripted: complexity-gate → lean; decide → conclusion with FR + calibrated confidence; act → recorded; converge-or-pass-cap → lean-complete
- Expect visited: [complexity-gate, decide, act, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: lean-complete

### S2 — Spiral converges on pass 1
- Inputs: `request = {text: "should we enter the German market?"}`
- Scripted: complexity-gate → spiral; observe/orient/decide/act → normal; self-attack → `material_disconfirmation = false`, evidence refs populated; converge → all four criteria hold
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: converged

### S3 — Spiral loops once, then converges
- Inputs: as S2
- Scripted: pass 1 self-attack → `material_disconfirmation = true`; converge → pass-count 1 < 4, cycle; pass 2 self-attack → false; converge → criteria met
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap, observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: converged

### S4 — Pass cap reached
- Inputs: `request = {text: "rigorous: will regulation X pass by 2027?"}`
- Scripted: self-attack → `material_disconfirmation = true` on every pass
- Expect visited: [complexity-gate] + 4 × [observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: pass-cap-residual-uncertainty (`residual-uncertainty` populated)

### S5 — Dispatched by a parent with forced spiral
- Inputs: `request` from parent dispatch payload, trigger `critical-thinking-spiral-needed` (forces spiral), parent `run_id`
- Scripted: complexity-gate → spiral regardless of table; pass 1 converges
- Expect visited: as S2 (recorded under the parent's call scope)
- Expect gates: []
- Expect terminal: converged (returned to the parent step as its outcome)

### S6 — Convergence faked, person says theatre
- Inputs: as S2
- Scripted: self-attack → `material_disconfirmation = false`, `evidence_actually_found = []`; converge → convergence-faked raised; person → theatre; self-attack (must-attack targets) → false with refs; converge → criteria met
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap, self-attack, converge-or-pass-cap]
- Expect gates: [convergence-faked review → theatre]
- Expect terminal: converged

### S7 — Convergence faked, autonomous mode
- Inputs: as S6, no person available
- Scripted: converge → convergence-faked raised
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: UNSTATED ("manual-review terminal"; not in the verdict vocabulary)

### S8 — Lean misclassified, promoted to spiral
- Inputs: `request = {text: "is this assumption sound: users will pay for sync?"}`
- Scripted: complexity-gate → lean; decide → a key claim Low confidence with no falsification condition; promotion → spiral (pass 1 counted); pass 2 converges
- Expect visited: [complexity-gate, decide, observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: converged

### S9 — Rebuttal unexamined
- Inputs: as S2
- Scripted: pass 1 → disconfirmation, cycle; pass 2 applied-record is a rebuttal; converge → rebuttal-unexamined; self-attack on the rebuttal → false with refs; converge → criteria met
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap, observe, orient, decide, act, self-attack, converge-or-pass-cap, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: converged

### S10 — Anti-thrash early stop
- Inputs: as S4
- Scripted: passes 2 and 3 revise the same load-bearing assumption back and forth
- Expect visited: [complexity-gate] + 3 × [observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: pass-cap-residual-uncertainty

### S11 — No material disconfirmation but criteria unmet (unrouted)
- Inputs: as S2
- Scripted: self-attack → false; converge → criterion (b) fails (a key claim lacks a falsification condition); pass-count 1
- Expect visited: [complexity-gate, observe, orient, decide, act, self-attack, converge-or-pass-cap]
- Expect gates: []
- Expect terminal: UNSTATED (no route matches; the engine must refuse the definition as non-exhaustive)

## Ambiguities for the process owner
- No route when `material-disconfirmation == false`, `convergence-criteria-met == false` and `pass-count < 4` (S11).
- The lean path runs `act` per transitions, but `act`'s and `decide`'s instructions say act is bypassed on lean.
- Four routes exist only in failure-mode prose or step instructions (rebuttal-unexamined, convergence-faked, complexity-misclassified, anti-thrash), not in transitions.
- `pass-count` initial value and when it increments (before or after the `< 4` test) are unstated; "4 passes" could mean 4 or 5 executions of observe.
- The route conditions are not mutually exclusive as written (e.g. lean-complete vs converged); only step instructions give an evaluation order.
- The convergence-faked human decision has no gate step, no vocabulary beyond genuine/theatre, and an autonomous "manual-review terminal" that is not one of the three verdicts.
- The forced-spiral flag from the critical-thinking trigger is not a declared input.
- `observe` reads `self-attack-result?` and `decide` reads `decomposition?`/`evidence-set?` as optional, but `self-attack` reads `decomposition` as required, which never exists after a lean→spiral promotion until orient runs.
- `spiral-trace` accumulates per pass (an append reducer), not declared.
- `complexity-gate` is labelled deterministic but its tiebreak is judgement ("when ambiguous").
