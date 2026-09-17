# Recursive refinement — fd

Source: fd-product-architecture/processes/recursive-refinement.process.yaml
Purpose: Classify a node as complex, complicated or clear and recurse — inquire, decompose, or mint a work package — until the tree bottoms out in conformant work packages.
Use cases: UC-IN-TYPED, UC-IN-FALLBACK, UC-IN-AMBIENT, UC-DECIDE, UC-PATHS, UC-ROUTE-DEFAULT, UC-CALL, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES, UC-FOREACH, UC-LOOP-BUDGET, UC-TERMINATES-WHEN, UC-STOP-HONEST, UC-STOP-NAMED, UC-PRECONDITION, UC-STATE-CHANNELS

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | entry_decision | decide (agent; no tool bound) | Cynefin: complex, complicated or clear. | `node_brief`, `solution_spec`, `contract_set` → `classification` |
| inquire | dispatch-grounded-inquiry | process-call (`grounded-inquiry`) | Resolves ambiguity with a governed inquiry; reads back verdict and recommendations. | `node_brief` → `recommendation`, `inquiry_verdict`, `sub_problems` |
| inquire | recurse-on-sub-problems | process-call per sub-problem (`recursive-refinement`) | Re-enters this process's entry decision for each sub-problem. | `sub_problems` → `work_package` (append) |
| decompose | wbs-decompose | tool (`wbs-decompose`) | WBS under the 100% rule; reads upstream Solution dispositions and contract set when present. | `[node_brief, brief]`, `governed_sources`, `solution_spec`, `contract_set` → `wbs_tree` |
| decompose | rolling-wave | process-call per ambiguous child (`recursive-refinement`) | Details clear children now; re-enters the controller for children still needing refinement. | `wbs_tree` → `wbs_tree` (extended) |
| decompose | completeness-gate | tool (`check-wbs-gate`), deterministic, precondition | SYM-1007 completeness + structural fidelity over the assembled DAG; mints on pass. | `wbs_tree`, `solution_spec`, `decompose_count` → `completeness_report`, `decompose_count`, `work_package` |
| execute | mint-work-package | tool (`mint-work-package`) | Mints one conformant work package and its execution request. | `[node_brief, brief]` → `work_package`, `execution_requests`, `stopped` |

## Routes as declared
- Entry decision (no tool bound): complex → `inquire`; complicated → `decompose`; clear → `execute`. Signal prose: a node arriving with `solution_spec` + `contract_set` is complicated when more than one disposition/contract entry remains, clear when exactly one.
  - Unrecognised classification → `complicated`: declared only in executor (`nodes_prose.py:134-135`, `compile.py:703`).
  - Depth bound: when `depth >= max_depth` (default 4) the first non-recursive path (`execute`) is forced — declared only in executor (`guards.py:24-26`, `compile.py:695-706`).
- inquire (`recursive: true`): `start: dispatch-grounded-inquiry` → `next: [recurse-on-sub-problems]` → `next: [end]`.
  - `dispatch-grounded-inquiry.on_fail` (prose): insufficient → stop the descent honestly. Route declared only in executor (`compile.py:709-717`: `stopped` → stop). At max depth the dispatch returns `deferred` and stops — declared only in executor (`dispatch.py:170-171`).
  - `terminates_when`: grounded-inquiry returns a signed-off recommendation whose sub-problems are each re-classified, OR insufficient.
- decompose (`recursive: true`): `start: wbs-decompose` → rolling-wave → completeness-gate → `next: [end]`; `completeness-gate.on_fail_goto: wbs-decompose`.
  - Reject loop budget: counter `decompose_count` (+1 per failed gate); retry while `decompose_count <= MAX_DECOMPOSE = 2` → at most 2 re-decompositions, then stop — declared only in executor (`guards.py:20-22`, `compile.py:720-732`).
  - `completeness-gate.precondition`: every branch bottomed out (clear leaf or honest inquire stop).
  - `terminates_when`: every leaf conformant AND the gate passes.
- execute (`recursive: false`): `start: mint-work-package` → `next: [end]`. `on_fail` (prose): not atomic → re-classify as complicated or complex (no edge). Executor records `stopped: leaf-not-conformant` and ends.
- Nested calls: fresh thread, `depth + 1`, `auto_sign_off = true`, `RECURSION_LIMIT = 60` per nested graph — declared only in executor (`dispatch.py:51-62`, `:114-139`).
- Terminal names (executor `stopped`): `stopped:insufficient`, `stopped:deferred`, `stopped:<gate-exhausted>` (stop node with no reason → `stopped`), `stopped:leaf-not-conformant`; normal `end`. Definition names none.

## Scenarios
### S1 — Clear node minted
- Inputs: `node_brief` = "Add a `locale` field to the survey-created event"
- Scripted: entry → clear; mint-work-package → 1 work_package + 1 execution_request
- Expect visited: [entry_decision, mint-work-package]
- Expect gates: []
- Expect terminal: end

### S2 — Clear node that is not atomic
- Inputs: `node_brief` = "Rebuild reporting"
- Scripted: entry → clear; mint-work-package → leaf fails WorkPackage validation
- Expect visited: [entry_decision, mint-work-package]
- Expect gates: []
- Expect terminal: stopped:leaf-not-conformant (executor). Definition on_fail prose would re-classify (no edge) — see ambiguities.

### S3 — Complicated node decomposes cleanly
- Inputs: `node_brief` = "Ship survey export to CSV and Parquet"
- Scripted: entry → complicated; wbs-decompose → 3 leaves + assembly node, none `needs_refinement`; completeness-gate → passed
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, completeness-gate]
- Expect gates: []
- Expect terminal: end (leaves minted)

### S4 — Rolling wave recurses into one child
- Inputs: as S3
- Scripted: wbs-decompose → child `parquet-writer` flagged `needs_refinement`; rolling-wave → `call:recursive-refinement(clear)→end` for that child; completeness-gate → passed
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, `call:recursive-refinement(execute)→end`, completeness-gate]
- Expect gates: []
- Expect terminal: end

### S5 — Completeness gate rejects once
- Inputs: as S3
- Scripted: completeness-gate#1 → failed (unbound term), decompose_count 1; wbs-decompose#2 → fixed tree; completeness-gate#2 → passed
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, completeness-gate, wbs-decompose, rolling-wave, completeness-gate]
- Expect gates: []
- Expect terminal: end

### S6 — Completeness gate budget exhausted
- Inputs: as S3
- Scripted: completeness-gate → failed on passes 1, 2, 3 (decompose_count 1, 2, 3)
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, completeness-gate, wbs-decompose, rolling-wave, completeness-gate, wbs-decompose, rolling-wave, completeness-gate]
- Expect gates: []
- Expect terminal: stopped (gate exhausted; declared only in executor, MAX_DECOMPOSE = 2)

### S7 — Upstream Solution with unfaithful WBS
- Inputs: `node_brief` = "Survey sharing"; `solution_spec` with dispositions [share-link: build, auth: reuse]; `contract_set` with 2 entries
- Scripted: entry → complicated; wbs-decompose → tree missing `auth` trace; completeness-gate#1 → fidelity reject; wbs-decompose#2 → faithful; gate#2 → passed
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, completeness-gate, wbs-decompose, rolling-wave, completeness-gate]
- Expect gates: []
- Expect terminal: end

### S8 — Complex node resolved by inquiry
- Inputs: `node_brief` = "Should respondents be able to pause long surveys?"
- Scripted: entry → complex; dispatch → `call:grounded-inquiry(single-inquiry)→end` with confidence grounded, 2 signed-off recommendations; recurse-on-sub-problems → each `call:recursive-refinement(execute)→end`
- Expect visited: [entry_decision, dispatch-grounded-inquiry, `call:grounded-inquiry(single-inquiry)→end`, recurse-on-sub-problems, `call:recursive-refinement(execute)→end` ×2]
- Expect gates: [nested grounded-inquiry recommend: permit (policy), nested sign-off: auto-permit]
- Expect terminal: end

### S9 — Inquiry insufficient: descent stops
- Inputs: as S8
- Scripted: dispatch → `call:grounded-inquiry(single-inquiry)→stopped:insufficient`
- Expect visited: [entry_decision, dispatch-grounded-inquiry, `call:grounded-inquiry(single-inquiry)→stopped:insufficient`]
- Expect gates: []
- Expect terminal: stopped:insufficient

### S10 — Depth limit forces a leaf
- Inputs: nested seed `depth = 4`, `max_depth = 4`, `node_brief` = an ambiguous sub-problem
- Scripted: entry classifier → complex (overridden)
- Expect visited: [entry_decision, mint-work-package]
- Expect gates: []
- Expect terminal: end (declared only in executor)

### S11 — Child inquiry halted before sign-off
- Inputs: as S8, no approval threshold declared anywhere
- Scripted: dispatch → `call:grounded-inquiry(single-inquiry)→stopped:recommend-indeterminate` with confidence partial and drafted (unapproved) recommendations
- Expect visited: [entry_decision, dispatch-grounded-inquiry, `call:grounded-inquiry(single-inquiry)→stopped:recommend-indeterminate`]
- Expect gates: [nested recommend: indeterminate → halt]
- Expect terminal: UNSTATED — best reading of `terminates_when`/verification (needs a signed-off recommendation): stop; executor recurses on the unapproved recommendations

### S12 — Classifier gives no usable answer
- Inputs: `node_brief` = "Do the thing"
- Scripted: entry classifier → "unknown"
- Expect visited: [entry_decision, wbs-decompose, rolling-wave, completeness-gate]
- Expect gates: []
- Expect terminal: end or stopped per gate — executor defaults to complicated (declared only in executor; spec §1 says MUST NOT proceed when no branch selected)

## Ambiguities for the process owner
- The depth bound (`max_depth = 4`), the forced non-recursive path at the bound, `deferred`, and `RECURSION_LIMIT = 60` are declared only in executor (`guards.py:17-26`, `dispatch.py:170-171`). Spec §7 requires a bound but the definition names no value.
- `MAX_DECOMPOSE = 2` and its counter are declared only in executor; the definition's `on_fail_goto: wbs-decompose` has no budget.
- The honest insufficient stop in `inquire` is prose; its route is declared only in executor.
- An unrecognised classification defaults to `complicated` in the executor, contradicting spec §1 (no default path) and UC-ROUTE-DEFAULT.
- Neither path's `terminates_when` is evaluated in routing (`guards.py:42-50` test-only). Spec §7 re-entry at `start` for a false predicate is not implemented.
- `mint-work-package.on_fail` ("re-classify") and `completeness-gate.on_fail` ("return to wbs-decompose / rolling-wave") name targets in prose that the edges do not all carry.
- `completeness-gate.precondition` (every branch bottomed out) is not evaluated; rolling-wave recursion is synchronous so it holds in the executor by construction.
- `recurse-on-sub-problems` and `rolling-wave` both declare `methodology_ref: recursive-refinement` with no input mapping; the executor passes the recommendation text (or child id) as `node_brief`. `path` is never forced (UC-CALL-PATH).
- The inquire path consumes grounded-inquiry's recommendations as sub-problems even when the child halted at `recommend` without approval (S11); nested runs also auto-permit sign-off (`dispatch.py:120`).
- `rolling-wave` in the executor passes the child's id as the child's brief (`dispatch.py:269-271`), not its description.
- `governed_sources` and `brief` (fallback) are read but not declared inputs.
