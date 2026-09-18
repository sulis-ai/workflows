# Solution delivery — fd

Source: fd-product-architecture/processes/solution-delivery.process.yaml
Purpose: Settle a software ask's architecture from grounded recon and pressure-tested shape decisions, get the Solution and its contract set approved, then hand it to recursive-refinement.
Use cases: UC-IN-TYPED, UC-IN-FALLBACK, UC-IN-AMBIENT, UC-OUT-TYPED, UC-VERDICT-ROUTE, UC-LOOP-BUDGET, UC-STOP-HONEST, UC-STOP-NAMED, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-REFUSAL-MODE, UC-APPROVAL-AUTO, UC-GATE-AUDIT, UC-GATE-CRITERIA, UC-PRECONDITION, UC-CALL, UC-CALL-PATH, UC-CALL-GATES

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (no framing, no entry_decision) | — | Single path `settle-and-deliver`. | — |
| settle-and-deliver | recon | tool (`grounded-recon`) | Finds existing components, contracts and declared-repo files the deliverable could reuse; drops uncited claims. | `brief`, `topology_index` → `findings`, `finding_instances`, `rejected_citations` |
| settle-and-deliver | resolve | tool (`resolve`) | Names open questions (knowledge vs authority) and searches for the knowledge ones, recording where it looked. | `[framed_question, brief]`, `governed_sources`, `findings` → `resolution` |
| settle-and-deliver | pressure-test-shape | tool (`pressure-test-shape`) + verdict gate | Shape check, disposition analysis, contract-kind classification, hardening lenses → survived/dropped/revised. | `findings`, `revise_count` → `insight`, `insight_verdicts`, `surviving_insights`, `revise_count` |
| settle-and-deliver | converge-confidence | tool (`converge-confidence`) | Sets grounded / partial / insufficient on the shape. | `surviving_insights` → `insight`, `confidence_verdict` |
| settle-and-deliver | author-solution | tool (`author-solution`) + approval gate (`on_refusal: halt`) | Drafts the Solution; gate licenses unsupervised drafting. | `surviving_insights`, `topology_index`, `findings`, `resolutions`, `design_spec` → `solution_spec` |
| settle-and-deliver | sign-off | approval gate (`on_refusal: halt`), tool `record-sign-off` | Stage-Gate go/no-go on the Solution. | `solution_spec` → `solution_spec`, `carried_unchanged` |
| settle-and-deliver | author-contracts | tool (`author-contracts`) + approval gate (`on_refusal: halt`), precondition signed off | Resolves the Solution's contract kinds into a concrete, grounded contract set. | `solution_spec`, `contract_forms`, `findings` → `contract_set` |
| settle-and-deliver | dispatch-recursive-refinement | process-call (`recursive-refinement`, no path forced) | Hands Solution + contract set to the controller, which classifies afresh. | `solution_spec`, `contract_set`, `brief` → `work_package` |

## Routes as declared
- Entry: none; `start: recon`; `recursive: false`.
- recon → resolve → pressure-test-shape.
- `pressure-test-shape.gate.on_verdict`: `survived → converge-confidence`, `dropped → end`, `revised → recon` (loop covers recon, resolve). Counter `revise_count`, budget `MAX_REVISE = 2` (loop taken at most twice; batch rule revised > survived > dropped) — declared only in executor (`guards.py:18`, `interrogate.py:90-103`).
- converge-confidence → `next: [author-solution]`. Insufficient: no route in definition; `author-solution.precondition` says an insufficient verdict "routes to human review (or the process's own insufficient stop)"; `sign-off.precondition` says it "does not proceed to dispatch". Executor: no stop here; gates evaluate `indeterminate` under insufficient (`domain/authorization.py:69-78`).
- Each approval gate (`author-solution`, `sign-off`, `author-contracts`): `permit` → `next`; else `on_refusal: halt`. Resolution order (declared only in executor, `authorization.py:36-131`): insufficient → indeterminate; human approval recorded for `solution-delivery:<step>` → permit; no threshold → indeterminate; tier unknown → indeterminate; tier ≥ threshold → permit; else indeterminate.
  - Executor diverges: a non-permit gate pauses for a person (`interrupt`) and a person's no-go stops with `<step>-no-go` (`nodes_code.py:425-502`).
- `sign-off.on_fail` (prose): deny/indeterminate routes back to `pressure-test-shape`. Conflicts with its own `on_refusal: halt`.
- author-contracts → dispatch-recursive-refinement → `call:recursive-refinement` → `next: [end]`. `dispatch.on_fail` (prose): if refinement cannot progress, return to sign-off's on_fail path (i.e. pressure-test-shape).
- Terminal names: UNSTATED; below `end`, `halted:<step>` (on_refusal halt), `stopped:insufficient`.

## Scenarios
### S1 — Everything licensed by policy
- Inputs: `brief` = "Let customers schedule recurring survey exports"; `design_spec` absent; threshold met for all three permissions
- Scripted: recon → 5 findings; resolve → 2 resolutions; pressure-test → [survived ×3]; converge → grounded; author-solution gate → permit (policy); sign-off → permit (policy); author-contracts gate → permit (policy); dispatch → `call:recursive-refinement(decompose)→end`
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off, author-contracts, dispatch-recursive-refinement, `call:recursive-refinement(decompose)→end`]
- Expect gates: [author-solution: permit (policy), sign-off: permit (policy), author-contracts: permit (policy)]
- Expect terminal: end

### S2 — Approvals recorded by people
- Inputs: as S1, no threshold; `human_approvals` for `solution-delivery:author-solution`, `:sign-off`, `:author-contracts`
- Scripted: as S1; child → `call:recursive-refinement(execute)→end` (small Solution classifies clear)
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off, author-contracts, dispatch-recursive-refinement, `call:recursive-refinement(execute)→end`]
- Expect gates: [author-solution: permit (human), sign-off: permit (human), author-contracts: permit (human)]
- Expect terminal: end

### S3 — Shape revised once
- Inputs: as S1
- Scripted: pressure-test#1 → [revised, survived]; recon#2, resolve#2; pressure-test#2 → [survived]; rest as S1
- Expect visited: [recon, resolve, pressure-test-shape, recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off, author-contracts, dispatch-recursive-refinement, `call:recursive-refinement(decompose)→end`]
- Expect gates: [author-solution: permit, sign-off: permit, author-contracts: permit]
- Expect terminal: end

### S4 — Shape revise budget exhausted, nothing survives
- Inputs: as S1
- Scripted: pressure-test#1,#2,#3 → [revised] (revise_count 1, 2, 3)
- Expect visited: [recon, resolve, pressure-test-shape, recon, resolve, pressure-test-shape, recon, resolve, pressure-test-shape]
- Expect gates: []
- Expect terminal: end (dropped)

### S5 — Every disposition dropped
- Inputs: as S1
- Scripted: pressure-test → [dropped, dropped] (build-where-reuse-exists caught)
- Expect visited: [recon, resolve, pressure-test-shape]
- Expect gates: []
- Expect terminal: end (dropped)

### S6 — Shape evidence insufficient
- Inputs: as S1
- Scripted: pressure-test → [survived]; converge → insufficient
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution]
- Expect gates: [author-solution: indeterminate (hard exception) → halt]
- Expect terminal: halted:author-solution (best reading: never auto-permits, `on_refusal: halt`); executor pauses for a person who may still approve

### S7 — Solution drafting not licensed
- Inputs: as S1, no threshold, no human approvals
- Scripted: converge → partial; author-solution gate → indeterminate
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution]
- Expect gates: [author-solution: indeterminate → halt]
- Expect terminal: halted:author-solution (executor: paused, then `stopped:author-solution-no-go` on a person's no)

### S8 — Solution rejected at sign-off
- Inputs: as S1 but sign-off threshold not met
- Scripted: author-solution → permit; sign-off → deny
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off]
- Expect gates: [author-solution: permit, sign-off: deny → halt]
- Expect terminal: halted:sign-off (per `on_refusal: halt`; `on_fail` prose would instead return to pressure-test-shape)

### S9 — Contract set not licensed
- Inputs: as S1 but author-contracts threshold not met
- Scripted: author-contracts gate → indeterminate
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off, author-contracts]
- Expect gates: [author-solution: permit, sign-off: permit, author-contracts: indeterminate → halt]
- Expect terminal: halted:author-contracts

### S10 — Refinement cannot make progress
- Inputs: as S1
- Scripted: dispatch → `call:recursive-refinement(decompose)→stopped` (completeness gate exhausted)
- Expect visited: [recon, resolve, pressure-test-shape, converge-confidence, author-solution, sign-off, author-contracts, dispatch-recursive-refinement, `call:recursive-refinement(decompose)→stopped`]
- Expect gates: [author-solution: permit, sign-off: permit, author-contracts: permit]
- Expect terminal: UNSTATED — `on_fail` prose returns to pressure-test-shape (no edge, no budget); executor ends at `end`

## Ambiguities for the process owner
- All three approval gates declare `on_refusal: halt`, but the executor pauses for a person on any non-permit (`nodes_code.py:425-502`). The schema's own description of `on_refusal` (`process.schema.json:595-600`) says solution-delivery's sign-off halts; the executor changed since.
- `sign-off` contradicts itself: `on_refusal: halt` versus `on_fail` "routes back to pressure-test-shape". Send-back target exists in prose only, with no budget.
- No declared route for `confidence_verdict == insufficient`. The two preconditions give different answers ("human review or insufficient stop" versus "does not proceed"). Unlike grounded-inquiry, the executor has no insufficient stop here, and a person's go at the paused gate bypasses the hard exception.
- `MAX_REVISE = 2`, its counter and the batch rule are declared only in executor.
- No threshold value exists anywhere in the register, so an unattended run always stops at `author-solution` (S7).
- `notify_ref` recipient is declared "honestly undecided" for all three gates: the person who must decide at a pause has no declared address.
- `dispatch-recursive-refinement` names no `path` on purpose; the input mapping (`solution_spec`, `contract_set` as seed) is declared only in executor (`compile.py:268-293`).
- Nested runs dispatched from here auto-permit sign-off inside recursive-refinement's grounded-inquiry calls (`dispatch.py:120`).
- `resolve` reads `framed_question`, which this process never produces (no framing); `topology_index`, `governed_sources`, `contract_forms` are read but not declared inputs.
- `resolve` "authority" questions must not be attempted, but no human input gate is declared to ask them.
