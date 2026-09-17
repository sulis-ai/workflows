# Change verification gate — fd

Source: fd-product-architecture/processes/change-verification-gate.process.yaml
Purpose: Routine per-change gate proving a component still meets its structural target and every owned contract still behaves per its profile.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-IN-AMBIENT, UC-STATE-CHANNELS, UC-PRECONDITION, UC-STOP-NAMED, UC-FAILURE-MODES, UC-TOOL-KINDS, UC-MECHANISM

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (no framing, no entry_decision) | — | Single path `verify`, invoked directly by an execution request. | — |
| verify | structural-conformance | tool (`structural-conformance`) | Runs the service-structure fitness function against the component's code. | `component_ref`, `component_sources`, `conformance_report` → `conformance_report` |
| verify | behavioural-conformance | tool (`behavioural-conformance`) | Runs every conformance scenario of every in-scope owned contract at its own declared tier, plus any registered Scenario covering the component. | `component_ref`, `component_sources`, `contract_refs`, `conformance_report` → `conformance_report` |
| verify | drift-check | tool (`drift-check`), guarded by precondition | Re-runs the component-tier scenarios for port contracts against the real adapter and compares with the fake. | `component_ref`, `component_sources`, `contract_refs`, `conformance_report` → `conformance_report` |

## Routes as declared
- Entry: none; `start: structural-conformance`; `recursive: false`.
- `structural-conformance` → `next: [behavioural-conformance]`. `on_fail` (prose): block the gate, do not proceed. No `verified_by`, no `on_fail_goto`.
- `behavioural-conformance` → `next: [drift-check]`. `on_fail` (prose): block the gate. No `verified_by`/`on_fail_goto`.
- `drift-check` → `next: [end]`. `precondition` (prose): at least one in-scope contract is a `port`; "otherwise this step is a no-op pass". `on_fail` (prose): block the gate, flag the drifted fake.
- Failure routing: spec §6 — a failure with neither `on_fail_goto` nor an honest stop MUST halt. Structural form: halt, reason = failing step. Executor: declared only in executor as "always forward" — `compile.py:817-883` wires only `next` edges, no stop node.
- Loops, budgets, approval gates, calls, recursion: none.
- Terminal verdict names: UNSTATED. Below: `end` (gate passed) and `halted:<step>` (spec §6 halt).

## Scenarios
### S1 — Change passes, port contract present
- Inputs: `component_ref` = `topology/components/survey-api`; `contract_refs` absent (all owned contracts)
- Scripted: structural-conformance → pass; behavioural-conformance → all scenarios pass at their tiers; drift-check precondition holds (one `port`) → real adapter agrees with fake
- Expect visited: [structural-conformance, behavioural-conformance, drift-check]
- Expect gates: []
- Expect terminal: end (conformance_report pass)

### S2 — No port contracts: drift-check is a no-op pass
- Inputs: `component_ref` = `topology/components/web-frontend`; `contract_refs` = [`rest_endpoint` contract only]
- Scripted: structural → pass; behavioural → pass; drift-check precondition false
- Expect visited: [structural-conformance, behavioural-conformance, drift-check (no-op pass)]
- Expect gates: []
- Expect terminal: end (conformance_report pass)

### S3 — Structural rule broken
- Inputs: `component_ref` = `topology/components/survey-api`
- Scripted: structural-conformance → error-severity finding (domain imports an adapter)
- Expect visited: [structural-conformance]
- Expect gates: []
- Expect terminal: halted:structural-conformance (per on_fail prose + spec §6; executor today proceeds to behavioural-conformance)

### S4 — Behavioural regression
- Inputs: `component_ref` = `topology/components/survey-api`; `contract_refs` = [`survey-api/create-survey`]
- Scripted: structural → pass; behavioural → contract-tier scenario previously green now fails (regression)
- Expect visited: [structural-conformance, behavioural-conformance]
- Expect gates: []
- Expect terminal: halted:behavioural-conformance

### S5 — Behavioural coverage gap
- Inputs: as S4
- Scripted: structural → pass; behavioural → contract missing required `error_handling` category
- Expect visited: [structural-conformance, behavioural-conformance]
- Expect gates: []
- Expect terminal: halted:behavioural-conformance (report names coverage gap, not regression)

### S6 — Fake has drifted
- Inputs: as S1
- Scripted: structural → pass; behavioural → pass; drift-check precondition holds → real adapter fails a scenario the fake passed
- Expect visited: [structural-conformance, behavioural-conformance, drift-check]
- Expect gates: []
- Expect terminal: halted:drift-check

## Ambiguities for the process owner
- No step declares a machine failure edge; every "block the gate" is prose. Spec §6 says halt; the reference executor runs all three steps regardless (`executor/service_layer/compile.py:817-883`). S3–S6 expected results differ between the two.
- "Block the gate" versus a successful run that produces a failing `conformance_report`: is a failing gate a halted run, or a completed run whose output says fail? Terminal verdict names are unstated.
- `drift-check`'s precondition says a false precondition is a "no-op pass"; spec §6 says a false precondition MUST NOT run the step and routes to `on_fail_goto`/halt. The definition overrides the spec's default without a structural marker.
- `component_sources` is read by every step but is not a declared input (host-provided, undeclared: UC-IN-AMBIENT).
- `conformance_report` is both read and written by each step; whether this is append (spec §8 collection) or replace is unstated per step.
- `contract_refs` absent means "every owned contract"; that default lives in prose, not as a declared `default`.
