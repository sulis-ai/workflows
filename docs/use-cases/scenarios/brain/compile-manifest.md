# compile-manifest — brain

Source: plugins/sulis-brain/instances/compile-manifest/workflow.jsonld
Purpose: Turn a generation goal and a declared source set into the closed, audience-scoped context manifest a faithful-generation-harness run consumes.
Use cases: UC-IN-TYPED, UC-OUT-MULTI, UC-OUT-TYPED, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-STOP-HONEST, UC-LOOP-BUDGET, UC-COMPENSATE, UC-FAILURE-MODES, UC-CRITICALITY, UC-MECHANISM, UC-TRIGGER, UC-CALL

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| gather-sources | mixed | Resolve only the declared sources → `gathered-context`, `unresolved-sources` | — (no tool_ref) |
| scope-to-audience | probabilistic | Select in-audience subset with reasons → `audience-scoped-subset` | — |
| atomise-variables | probabilistic | Decompose into `{variable_id, meaning, value, source}` → `manifest` | — |
| verify-closure | mixed | Shape, provenance, grounding sample, closure → `manifest`, `closure-valid`, `variable-count`, `final-verdict` | — |

## Routes as declared
- `gather-sources -> scope-to-audience [if at least one declared source RESOLVED to readable context — unresolved sources are recorded in unresolved-sources but do not block as long as a non-empty resolved set exists]`
  → condition `len(gathered-context) > 0`.
- `gather-sources -> [terminal:sources-insufficient] [if NO declared source resolves (all paths/refs dangling) — sources-unresolvable FailureMode fires; honest 'the inputs do not exist' rather than compiling an empty manifest]`
  → condition `len(gathered-context) == 0` → terminal `sources-insufficient` (honest stop).
- `scope-to-audience -> atomise-variables` → unconditional.
- `atomise-variables -> verify-closure` → unconditional.
- `verify-closure -> [terminal:manifest-ready] [if closure-valid (…) AND variable-count > 0]`
  → condition `closure-valid == true AND variable-count > 0` → terminal `manifest-ready`.
- `verify-closure -> scope-to-audience [if a structural fault is REPAIRABLE — e.g. a duplicate variable_id or an over-broad subset that pulled in out-of-audience context — re-scope and re-atomise]`
  → loop back to scope-to-audience; condition value UNSTATED (no "repairable" key in state); budget UNSTATED; invalidates `audience-scoped-subset`, `manifest` (implied).
- `verify-closure -> [terminal:sources-insufficient] [if after scoping+atomising the manifest is EMPTY (the resolved sources are well-formed but none bears on this goal+audience) — manifest-not-closed FailureMode fires; honest 'the inputs do not cover this artifact']`
  → condition `variable-count == 0` → terminal `sources-insufficient`.

## Scenarios
### S1 — manifest ready
- Inputs: `generation-goal: "consumer data contract for session manager"`, `artifact-audience: "engineer-facing consumer data contract"`, `declared-sources: [{kind: adr, ref: ADR-012}, {kind: convention, ref: CF-03}]`
- Scripted: gather-sources → both resolve; scope-to-audience → subset (lifecycle excluded); atomise-variables → 12 variables; verify-closure → `closure-valid: true`, `variable-count: 12`, `final-verdict: manifest-ready`
- Expect visited: [gather-sources, scope-to-audience, atomise-variables, verify-closure]
- Expect gates: []
- Expect terminal: manifest-ready

### S2 — some sources unresolved, still ready
- Inputs: as S1 plus `{kind: file, ref: docs/missing.md}`
- Scripted: gather-sources → `unresolved-sources: [docs/missing.md]`, two resolved; rest as S1
- Expect visited: [gather-sources, scope-to-audience, atomise-variables, verify-closure]
- Expect gates: []
- Expect terminal: manifest-ready

### S3 — no source resolves
- Inputs: `declared-sources: [{kind: entity, ref: dna:x:missing}]`
- Scripted: gather-sources → `gathered-context: {}`; sources-unresolvable fires
- Expect visited: [gather-sources]
- Expect gates: []
- Expect terminal: sources-insufficient

### S4 — repairable fault, re-scope once
- Inputs: as S1
- Scripted: verify-closure pass 1 → duplicate `variable_id` (repairable), `closure-valid: false`; scope-to-audience → narrower subset; atomise → 10 variables; verify-closure pass 2 → valid
- Expect visited: [gather-sources, scope-to-audience, atomise-variables, verify-closure, scope-to-audience, atomise-variables, verify-closure]
- Expect gates: []
- Expect terminal: manifest-ready

### S5 — repair loop never clears
- Inputs: as S1
- Scripted: verify-closure → repairable fault on every pass
- Expect visited: [gather-sources, (scope-to-audience, atomise-variables, verify-closure) repeated — no budget declared]
- Expect gates: []
- Expect terminal: UNSTATED (no exhaustion route)

### S6 — sources resolve but none bear on the goal
- Inputs: `generation-goal: "billing API contract"`, sources as S1
- Scripted: scope-to-audience → empty include list; atomise → `[]`; verify-closure → `variable-count: 0`; manifest-not-closed fires
- Expect visited: [gather-sources, scope-to-audience, atomise-variables, verify-closure]
- Expect gates: []
- Expect terminal: sources-insufficient

## Ambiguities for the process owner
- The repair loop has no budget and no exhaustion route.
- "Repairable" is a judgement with no state key; a non-empty manifest with a non-repairable fault (e.g. an ungrounded value, orphan provenance) has no declared route — the three verify-closure routes are not exhaustive.
- Both failure modes are `escalate` + `blocks_progress: true`, but the routes treat them as honest terminal stops (success of the process); which wins is unclear.
- verify-closure writes `manifest` again (removing ungrounded values) — a replace reducer is implied, not declared.
- `terminal_steps` lists only `verify-closure`, although gather-sources can also terminate.
- The deterministic source resolution in gather-sources has no tool; kinds `file|adr|convention|entity` are prose.
- `final-verdict` is not written on the gather-sources early stop.
