# harness-driver — brain

Source: plugins/sulis-brain/instances/harness-driver/workflow.jsonld
Purpose: Take one benchmark case, run it through the change engine, and independently judge the result into a two-gate per-case scorecard (behaviour gate, then a correctness gate that re-executes held-out scenarios against the landed artifact and never reads the engine's own verdict).
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-IN-OPTIONAL, UC-DECIDE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-VERDICT-ROUTE, UC-STOP-NAMED, UC-PRECONDITION, UC-CRITICALITY, UC-FAILURE-MODES, UC-SIDE-EFFECT-CLAIM, UC-TOOL-EFFECT, UC-TOOL-KINDS, UC-TOOL-RUNNER, UC-MECHANISM, UC-TRIGGER, UC-FOREACH (at the harness level, outside this definition)

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| validate-case | deterministic | Rejects a malformed case before any engine work; `case` → `validated-case` (bool) | validate-case-wellformed (python_import, query) |
| to-brief | deterministic | Derives `{name, intent, acceptance}`; withholds expected/held_out/engine_authored from the engine | case-to-brief (python_import, query) |
| invoke-engine | mixed | Runs the brief through the change engine; returns `{verdict, cause, landed, ...}` (landed is workspace-relative) | invoke-change-engine (mcp_server `change_run_stage`, side-effect) |
| read-outcome | deterministic | Normalises engine result to `produced\|refused\|noop\|cant-build\|failed` | read-engine-outcome (python_import, query) |
| to-run-record | deterministic | Wraps outcome string as `{'outcome': ...}` for gate-1 | engine-outcome-to-run-record (python_import, query) |
| gate-1 | deterministic | Behaviour gate: `produced_or_correctly_refused(run_record, expected)` → `behaviour-gate` (bool); forks produced/refused | gate-produced-or-refused (python_import, query) |
| run-held-out | deterministic | Correctness gate: re-executes held-out scenarios against the absolute landed path → `held-out-coverage` | reality-gate-held-out (python_import `_reality_gate`, query) |
| to-coverage | deterministic | Reduces reality-gate result to passed/total float | coverage-of-reality-gate (python_import, query) |
| to-compliance | deterministic | Measures archetype compliance of landed code (default archetype `library`); `None` when no checks | tool_ref compliance-from-flags; prose binds four: standard-checks-for, hard-checks-filter, run-standard-checks (mcp_server, side-effect), compliance-from-flags |
| check-independence | deterministic | Proves held-out set is disjoint from engine-authored scenarios → `independence-ok` (bool) | check-held-out-independence (python_import, query) |
| classify | deterministic | `classify_case_result(expected, produced_build, coverage, compliance)` → `pass\|fail-should-refuse\|fail-blocked\|fail-coverage\|fail-compliance` | classify-case-result (python_import, query) |
| to-record | deterministic | Shapes `{stage, verdict}` | verdict-to-case-record (python_import, query) |
| score | deterministic | `aggregate_scorecard([case-record])` then `overall_capability_rate` → `scorecard` | aggregate-scorecard (python_import, query); overall-capability-rate named in prose only |

No parallel starts, fan-out or joins are declared inside this process: one initial step, every route is exclusive. The fan-out is the trigger `per-case-dispatch`: the suite harness runs this process once per case (a for-each owned by the caller). `classify` is a merge point of two mutually exclusive routes (refused path, disjoint path), not a join.

## Routes as declared
- `validate-case -[malformed]-> [terminal:invalid-case]` → condition `validated-case == false` → terminal verdict `invalid-case`.
- `validate-case -[wellformed]-> to-brief` → condition `validated-case == true`.
- `to-brief -> invoke-engine` → unconditional.
- `invoke-engine -> read-outcome` → unconditional.
- `read-outcome -> to-run-record` → unconditional.
- `to-run-record -> gate-1` → unconditional.
- `gate-1 -[produced]-> run-held-out` → condition on `engine-outcome == produced` (best reading; `behaviour-gate` is a bool that means "did the right thing", not "produced"). See ambiguities.
- `gate-1 -[refused]-> classify` → condition on `engine-outcome != produced` (best reading). UNSTATED for `noop`, `cant-build`, `failed`.
- `run-held-out -> to-coverage` → unconditional.
- `to-coverage -> to-compliance` → unconditional.
- `to-compliance -> check-independence` → unconditional.
- `check-independence -[disjoint]-> classify` → condition `independence-ok == true`.
- `check-independence -[overlap]-> [terminal:invalid-case]` → condition `independence-ok == false` → terminal verdict `invalid-case` (prose names it "invalid-case (held-out leaks engine-authored)").
- `classify -> to-record` → unconditional.
- `to-record -> score` → unconditional.
- `score -> [terminal:scored]` → terminal verdict `scored`.

## Scenarios
### S1 — Produced, independent, passing
- Inputs: `case = {name: "add-two", intent: "add two ints", acceptance: [...], stage: "build", expected: "build", held_out: [{args:[1,2],expect:3}], engine_authored: [{args:[0,0],expect:0}], ...}`
- Scripted: validate-case → true; invoke-engine → `{verdict: pass, landed: "src/brain_runtime_runner/add_two.py"}`; read-outcome → `produced`; gate-1 → true; run-held-out → `{conforms: true, results:[{ok:true}]}`; to-coverage → 1.0; to-compliance → 1.0; check-independence → true; classify → `pass`
- Expect visited: [validate-case, to-brief, invoke-engine, read-outcome, to-run-record, gate-1, run-held-out, to-coverage, to-compliance, check-independence, classify, to-record, score]
- Expect gates: []
- Expect terminal: scored (scorecard carries one `pass` for stage `build`)

### S2 — Malformed case
- Inputs: `case = {name: "x"}` (missing intent/acceptance)
- Scripted: validate-case → false
- Expect visited: [validate-case]
- Expect gates: []
- Expect terminal: invalid-case (engine never invoked)

### S3 — Engine correctly refuses
- Inputs: case with `expected: "refuse"`
- Scripted: invoke-engine → `{verdict: refused}`; read-outcome → `refused`; gate-1 → true; classify (coverage and compliance absent) → `pass`
- Expect visited: [validate-case, to-brief, invoke-engine, read-outcome, to-run-record, gate-1, classify, to-record, score]
- Expect gates: []
- Expect terminal: scored

### S4 — Engine refuses a case expected to build (legitimate per-case fail)
- Inputs: case with `expected: "build"`
- Scripted: read-outcome → `refused`; gate-1 → false; classify → `fail-blocked`
- Expect visited: [validate-case, to-brief, invoke-engine, read-outcome, to-run-record, gate-1, classify, to-record, score]
- Expect gates: []
- Expect terminal: scored (failure mode engine-refused-expected-build is `fallback`, never aborts)

### S5 — Held-out leaks engine-authored
- Inputs: case whose `held_out` shares an example with `engine_authored`
- Scripted: read-outcome → `produced`; gate-1 → true; run-held-out → conforms; to-coverage → 1.0; to-compliance → 1.0; check-independence → false
- Expect visited: [validate-case, to-brief, invoke-engine, read-outcome, to-run-record, gate-1, run-held-out, to-coverage, to-compliance, check-independence]
- Expect gates: []
- Expect terminal: invalid-case

### S6 — Produced but held-out coverage fails
- Inputs: as S1
- Scripted: gate-1 → true; run-held-out → `{conforms:false, results:[{ok:true},{ok:false}]}`; to-coverage → 0.5; to-compliance → 1.0; check-independence → true; classify → `fail-coverage`
- Expect visited: as S1
- Expect gates: []
- Expect terminal: scored

### S7 — No compliance checks (honest N/A)
- Inputs: as S1, archetype resolves to no hard checks
- Scripted: to-compliance → `None`; classify treats compliance as skip-gate → `pass`
- Expect visited: as S1
- Expect gates: []
- Expect terminal: scored

### S8 — Engine no-op (outcome outside produced/refused)
- Inputs: case with `expected: "build"`
- Scripted: read-outcome → `noop`; gate-1 → false
- Expect visited: [validate-case, to-brief, invoke-engine, read-outcome, to-run-record, gate-1, classify, to-record, score] (best reading: treated as the refused fork; failure mode text says "refused (or no-op'd)")
- Expect gates: []
- Expect terminal: scored (`fail-blocked`)

## Ambiguities for the process owner
- gate-1 routes on `produced`/`refused` labels, but its only output `behaviour-gate` is a bool meaning "did the right thing". A correct refusal and a correct production are both `true`, so the fork cannot be evaluated from `behaviour-gate`; it needs `engine-outcome`.
- `noop`, `cant-build` and `failed` outcomes have no declared route out of gate-1.
- The case fields read by steps (`expected`, `stage`, `held-out-scenarios`, `engine-authored-scenarios`) are not in `state_contract`; only `case:ref` is. They are also not declared as ambient inputs.
- `classify` reads `held-out-coverage-rate` and `compliance-rate` on the refused path where they never exist; neither is marked optional (`?`).
- `check-independence` runs after correctness has been measured, and never runs on the refused path. An invalid case is only detected after engine work and scoring are spent.
- Two different terminal texts for one verdict: `invalid-case` and "invalid-case (held-out leaks engine-authored)". One verdict or two?
- `score` is listed in `terminal_steps` alongside `[terminal:scored]`, and `score` itself has an outgoing route.
- `to-compliance` binds four tools in prose but `tool_ref` names only compliance-from-flags; the composite (with one side-effect child) is not structural.
- `run-held-out` and `to-compliance` declare preconditions in prose ("gate-1 forked 'produced'"), not as evaluable conditions.
- Failure mode independence-violated is `abort` but names no terminal verdict; it is a policy on which inputs a step may read ("engine-verdict/engine-outcome are FORBIDDEN inputs"), which the schema cannot express.
- invoke-engine is a side-effect with no failure mode, retry or claim declared; an engine crash has no route.
- 15 of 19 tools are `python_import`, which the corpus walk found to complete silently with no runner.
- Tools reliability-rate and is-grounded are declared but bound to no step.
- The landed-path join (workspace root + relative `landed`) is a data transformation stated only in prose; no step owns it.
