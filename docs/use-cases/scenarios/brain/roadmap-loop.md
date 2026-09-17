# roadmap-loop — brain

Source: plugins/sulis-brain/instances/roadmap-loop/workflow.jsonld
Purpose: Pick the next provable requirement, build it through the change engine, independently prove it with a reality gate, then record the result and commit to the one PR, or block.
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-OUT-MULTI, UC-DECIDE, UC-VERDICT-ROUTE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-PATHS, UC-OPTIONAL-BRANCH, UC-STOP-NAMED, UC-STOP-HONEST, UC-RETRY, UC-FAILURE-MODES, UC-SIDE-EFFECT-CLAIM, UC-TOOL-EFFECT, UC-TOOL-RUNNER, UC-MECHANISM, UC-TRIGGER, UC-CALL (as a callee of change-lifecycle `deliver`)

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| pick-work | deterministic | Selects the next eligible not-verified requirement and runnable scenarios; none → idle → `chosen-requirement`, `runnable-scenarios` | pick-next-requirement (subprocess `loop_picker --requirement-ref`, query) |
| drive-engine | mixed | If the function already exists, verify it without rebuilding; else drive the change engine to synthesise it → `engine-verdict`, `landed-artifact` | drive-change-engine (mcp_server `change_run_stage`, side-effect) |
| reality-gate | deterministic | Re-executes acceptance against the landed function; never trusts the engine → `gate-verdict` | reality-gate (subprocess `reality_gate_cli`, query) |
| classify | deterministic | `ship \| handwrite \| blocker` from engine + gate verdicts → `disposition` | classify-disposition (subprocess `classify_disposition_cli`, query; unfilled args default to blocked) |
| record-and-ship | mixed | On ship: TestResult + mark verified + commit (never merge) → `testresult`, `commit` | record-and-ship (subprocess `deliver_land_cli.py`, side-effect, timeout 3600 s) |

No parallel starts, fan-out or joins: a single line with early exits. The trigger `scheduled-tick` (timer, ~10 min) runs one cycle per tick; the loop over the roadmap is the scheduler, not the definition.

## Routes as declared
- `pick-work -[none]-> [terminal:idle]` → condition on a pick status (no state key; best reading `chosen-requirement` empty) → terminal verdict `idle`.
- `pick-work -[no-acceptance]-> [terminal:blocked]` → condition on pick status `no-acceptance` (no state key) → terminal verdict `blocked`.
- `pick-work -[picked]-> drive-engine` → condition on pick status `picked`.
- `drive-engine -[pass]-> reality-gate` → condition `engine-verdict == pass`.
- `drive-engine -[blocked]-> [terminal:blocked]` → condition `engine-verdict == blocked` → terminal verdict `blocked`.
- `drive-engine -[refused]-> [terminal:blocked]` → condition `engine-verdict == refused` → terminal verdict `blocked`.
- `reality-gate -[conforms]-> classify` → condition `gate-verdict == conforms`.
- `reality-gate -[nonconforming]-> [terminal:blocked]` → condition `gate-verdict == nonconforming` → terminal verdict `blocked`.
- `classify -[ship]-> record-and-ship` → condition `disposition == ship`.
- `classify -[blocker]-> [terminal:blocked]` → condition `disposition == blocker` → terminal verdict `blocked`.
- `record-and-ship -> [terminal:shipped]` → terminal verdict `shipped`.
- Failure mode engine-blocked (retry) → "bounded hand-write (agent executor) then RE-ENTER the reality gate", i.e. `drive-engine` blocked → hand-write → `reality-gate`; budget UNSTATED; conflicts with the `blocked` route above.

## Scenarios
### S1 — Build, prove, ship
- Inputs: `roadmap-source` (host), `requirement_ref = "dna:requirement:..."` (when called by change-lifecycle)
- Scripted: pick-work → picked `add_two` with 2 scenarios; drive-engine → `pass`, landed `src/brain_runtime_runner/add_two.py`; reality-gate → conforms; classify → ship; record-and-ship → TestResult + commit
- Expect visited: [pick-work, drive-engine, reality-gate, classify, record-and-ship]
- Expect gates: []
- Expect terminal: shipped

### S2 — Nothing to pick
- Inputs: roadmap with every requirement verified
- Scripted: pick-work → none
- Expect visited: [pick-work]
- Expect gates: []
- Expect terminal: idle

### S3 — Requirement has no acceptance
- Scripted: pick-work → no-acceptance
- Expect visited: [pick-work]
- Expect gates: []
- Expect terminal: blocked

### S4 — Engine blocked
- Scripted: pick-work → picked; drive-engine → blocked (hand-write disabled)
- Expect visited: [pick-work, drive-engine]
- Expect gates: []
- Expect terminal: blocked

### S5 — Engine refused (no oracle)
- Scripted: drive-engine → refused
- Expect visited: [pick-work, drive-engine]
- Expect gates: []
- Expect terminal: blocked (failure mode no-oracle-refused, abort)

### S6 — Built but gate does not conform
- Scripted: drive-engine → pass; reality-gate → nonconforming (stub)
- Expect visited: [pick-work, drive-engine, reality-gate]
- Expect gates: []
- Expect terminal: blocked (requirement state unchanged)

### S7 — Classified as blocker
- Scripted: drive-engine → pass; reality-gate → conforms; classify → blocker
- Expect visited: [pick-work, drive-engine, reality-gate, classify]
- Expect gates: []
- Expect terminal: blocked

### S8 — Engine blocked, hand-write recovers (failure-mode path)
- Inputs: `handwrite_enabled = true`
- Scripted: drive-engine → blocked; hand-write by agent executor; reality-gate → conforms; classify → ship; record-and-ship → commit
- Expect visited: [pick-work, drive-engine, reality-gate, classify, record-and-ship] (hand-write is not a declared step)
- Expect gates: []
- Expect terminal: shipped

### S9 — Verify existing element
- Scripted: pick-work → picked `add_two` already on disk; drive-engine → verify-existing (no rebuild) → pass; reality-gate → conforms; classify → ship
- Expect visited: [pick-work, drive-engine, reality-gate, classify, record-and-ship]
- Expect gates: []
- Expect terminal: shipped

### S10 — Classified as handwrite (unrouted)
- Scripted: drive-engine → pass; reality-gate → conforms; classify → handwrite
- Expect visited: [pick-work, drive-engine, reality-gate, classify]
- Expect gates: []
- Expect terminal: UNSTATED (no route for `handwrite`)

## Ambiguities for the process owner
- `classify` can output `handwrite`, which has no route.
- engine-blocked failure mode says retry via hand-write then re-enter the reality gate; the transition sends `blocked` straight to `terminal:blocked`. The hand-write budget is UNSTATED and the flag (`handwrite_enabled`) is not a declared input.
- The description says four branches exist only in code ("code is authoritative"): a readiness gate at pick, a builder-kind route (function delivers, contract/workflow park), the verify-existing fork, and a flag-gated self-heal on the blocker path that parks work for off-path maintenance. None are modelled.
- pick-work's route labels (`none`, `no-acceptance`, `picked`) and gate labels (`conforms`, `nonconforming`) have no state key holding them; `gate-verdict` is a string with no enum.
- `roadmap-source` (read by pick-work) and `commit` (written by record-and-ship) are not in `state_contract`.
- Tool arguments (`requirement_ref`, `fn_name`, `landed_path`, `acceptance`, `scenario_ref`, `verdict`, `conforms`, `handwrite_enabled`, `slug`, `user`, `message`) are not declared inputs; classify-disposition's own note says `verdict/conforms/handwrite_enabled` are not threaded and it defaults to blocked.
- record-and-ship describes an "on blocker" behaviour (loop marker) that is unreachable because blocker routes to a terminal.
- `record-and-ship` is listed in `terminal_steps` and has an outgoing route.
- `drive-engine` and `record-and-ship` are side-effects (engine synthesis, a commit) with no claim, idempotency or retry declared; a rerun after a crash may commit twice.
- `blocked` collapses five causes (no acceptance, engine blocked, refused, nonconforming, blocker); callers cannot tell them apart from the verdict.
