# specify — brain

Source: plugins/sulis-brain/instances/specify/workflow.jsonld
Purpose: Write down what to build by dispatching the three existing capture tools in dependency order: capture the opportunity (why), author the requirement sourced from it (what), and author acceptance scenarios that verify it (verify).
Use cases: UC-IN-TYPED, UC-IN-AMBIENT, UC-OUT-TYPED, UC-VERDICT-ROUTE, UC-ROUTE-EXPR, UC-STOP-NAMED, UC-FOREACH, UC-PRECONDITION, UC-CRITICALITY, UC-FAILURE-MODES, UC-SIDE-EFFECT-CLAIM, UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-CAPABILITY, UC-MECHANISM, UC-TRIGGER, UC-CALL (as a callee of change-lifecycle `specify`)

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| capture-opportunity | mixed | Agent writes the job statement; tool mints and validates the Opportunity → `opportunity-ref` | needs `opportunity-capture` → emit-opportunity (subprocess `emit_opportunity.py`, side-effect) |
| author-requirement | mixed | Agent writes the shall-statement; tool mints the Requirement with `--source` = `opportunity-ref` → `requirement-ref` | needs `requirement-authoring` → emit-requirement (subprocess `emit_requirement.py`, side-effect) |
| author-scenarios | mixed | Agent writes one or more acceptance scenarios; tool mints each with `--verifies` = `requirement-ref` → `scenario-refs`, `final-outcome` | needs `scenario-authoring` → emit-scenario (subprocess `emit_scenario.py`, side-effect, invoked once per scenario) |

No parallel starts or joins. `author-scenarios` repeats its tool once per scenario inside one step (a for-each not declared structurally; whether invocations run in parallel is unstated).

## Routes as declared
- `capture-opportunity -> author-requirement [emit_opportunity minted the Opportunity (the WHY / job-statement) — opportunity-ref exists and can source the requirement]` → condition `opportunity-ref` present (tool accepted).
- `capture-opportunity -> [terminal:blocked] [emit_opportunity REFUSED the instance (schema-invalid job-statement) — there is no why-root to source the requirement from; do not author a requirement unmoored from an opportunity]` → condition: tool refused (no state key) → terminal verdict `blocked`.
- `author-requirement -> author-scenarios [emit_requirement minted the Requirement (the WHAT) with source == step-1's opportunity-ref — requirement-ref exists and can be verified]` → condition `requirement-ref` present AND its source == `opportunity-ref`.
- `author-requirement -> [terminal:blocked] [emit_requirement REFUSED the instance, OR its source is not step-1's opportunity-ref — the what would be unmoored from the why; the why->what link is broken]` → condition: refused OR source mismatch → terminal verdict `blocked`.
- `author-scenarios -> [terminal:specified] [emit_scenario minted one or more acceptance Scenarios (the VERIFY), each verifying step-2's requirement-ref — the why->what->verify chain is whole and brain-addressable; final-outcome == specified]` → condition `final-outcome == specified` → terminal verdict `specified`.
- `author-scenarios -> [terminal:blocked] [emit_scenario REFUSED the instance, OR no scenario verifies step-2's requirement-ref — the what has no verify; the what->verify link is broken; final-outcome == blocked]` → condition `final-outcome == blocked` → terminal verdict `blocked`.
- Failure mode broken-why-what-verify-chain (escalate) → "re-run the offending step passing the EXACT id" (a retry of author-requirement or author-scenarios); budget UNSTATED; conflicts with the `blocked` routes above.
- Failure mode reimplemented-capture-instead-of-dispatched (abort) → replace with a real dispatch; no route.

## Scenarios
### S1 — Chain whole
- Inputs: `subject-ref = "dna:change:... (CSV export)"`; tool flags `--for-product dna:product:...`, `--journey dna:workflow:...` (host)
- Scripted: emit-opportunity → `dna:opportunity:A`; emit-requirement (`--source A`) → `dna:requirement:B`; emit-scenario ×2 (`--verifies B`) → `[dna:scenario:C1, C2]`
- Expect visited: [capture-opportunity, author-requirement, author-scenarios]
- Expect gates: []
- Expect terminal: specified

### S2 — Opportunity refused
- Inputs: as S1
- Scripted: emit-opportunity → refused (job statement not in "When…, …can…" form)
- Expect visited: [capture-opportunity]
- Expect gates: []
- Expect terminal: blocked

### S3 — Requirement refused
- Scripted: emit-opportunity → A; emit-requirement → refused
- Expect visited: [capture-opportunity, author-requirement]
- Expect gates: []
- Expect terminal: blocked

### S4 — Requirement sourced from the wrong opportunity
- Scripted: emit-opportunity → A; emit-requirement accepted with `--source dna:opportunity:Z`
- Expect visited: [capture-opportunity, author-requirement]
- Expect gates: []
- Expect terminal: blocked (per transitions; the failure mode would instead re-run author-requirement)

### S5 — Mis-threaded id repaired by re-run (failure-mode path)
- Scripted: emit-requirement pass 1 → source Z (mismatch); re-run with `--source A` → B; emit-scenario → C1
- Expect visited: [capture-opportunity, author-requirement, author-requirement, author-scenarios]
- Expect gates: []
- Expect terminal: specified

### S6 — Scenario refused
- Scripted: A, B minted; emit-scenario → refused (no `verifies`)
- Expect visited: [capture-opportunity, author-requirement, author-scenarios]
- Expect gates: []
- Expect terminal: blocked

### S7 — Several scenarios, one refused, one accepted
- Scripted: A, B minted; emit-scenario #1 → refused; #2 → C2 verifying B
- Expect visited: [capture-opportunity, author-requirement, author-scenarios]
- Expect gates: []
- Expect terminal: specified (best reading: "at least one Scenario verifies"; the blocked route's "REFUSED the instance" also matches)

## Ambiguities for the process owner
- The blocked routes and the broken-chain failure mode disagree: transitions stop at `blocked`, the failure mode re-runs the offending step. No retry budget.
- With several scenarios, "emit_scenario REFUSED the instance" (blocked) and "at least one Scenario verifies" (specified) can both be true (S7).
- Tool refusal is not a state value; the first two route conditions cannot be evaluated from `state_contract`.
- `--for-product` and `--journey` are required tool flags with no declared input.
- `author-scenarios` is listed in `terminal_steps` and routes to two terminals.
- Every tool mints a new ULID; a re-run after a crash creates duplicate Opportunities/Requirements/Scenarios. No claim or idempotency key.
- A partially specified chain (opportunity minted, requirement refused) leaves orphan entities; whether they are undone is unstated.
- Failure-mode `escalate` has no person or gate step to escalate to.
