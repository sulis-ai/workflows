# Grounded inquiry — fd

Source: fd-product-architecture/processes/grounded-inquiry.process.yaml
Purpose: Answer a brief with sourced findings, insights that survived refutation and signed-off recommendations handed to work — or stop honestly when the evidence does not reach.
Use cases: UC-IN-TYPED, UC-IN-FALLBACK, UC-IN-AMBIENT, UC-OUT-MULTI, UC-OUT-TYPED, UC-STATE-CHANNELS, UC-PREPHASE, UC-DECIDE, UC-PATHS, UC-VERDICT-ROUTE, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-STOP-HONEST, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-TERMINATES-WHEN, UC-FOREACH, UC-JOIN, UC-CALL, UC-CALL-DEPTH, UC-CALL-GATES, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-REFUSAL-MODE, UC-APPROVAL-AUTO, UC-GATE-AUDIT, UC-PRECONDITION, UC-FIDELITY

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | framing | agent (prose) | Records the question verbatim, names presuppositions, commits to a framed question. | `brief` → `framing`, `framed_question` |
| — | entry_decision | decide (agent; no tool bound) | Atomic brief, or decomposes into sub-inquiries? | `framed_question`/`brief` → `path` |
| single-inquiry | gather-analyse-ground | tool (`grounded-recon`) | Gathers evidence, binds each finding to a source, drops unsourced claims. | `[framed_question, brief]`, `topology_index` → `findings`, `finding_instances`, `rejected_citations` |
| single-inquiry | interrogate | tool (`interrogate`) + verdict gate | 5-whys/ACH/premortem/refutation per claim → survived/dropped/revised. | `[hypotheses, findings]`, `revise_count` → `insight`, `insight_verdicts`, `surviving_insights`, `revise_count` |
| single-inquiry | converge-confidence | tool (`converge-confidence`) | Sets grounded / partial / insufficient. | `surviving_insights` → `insight`, `confidence_verdict` |
| single-inquiry | conclude | tool (`conclude`) | Prose answer resting on surviving insights. | `surviving_insights`, `confidence_verdict` → `conclusion` |
| single-inquiry | recommend | tool (`recommend`) + approval gate (`on_refusal: halt`) | Drafts recommendations; gate decides whether drafting unsupervised was licensed. | `surviving_insights`, `[framed_question, brief]` → `recommendation` (+ gate verdict) |
| single-inquiry | check-recommendation-fidelity | tool (`check-recommendation-fidelity`) + verdict gate | NLI entailment of each recommendation against cited insights. | `recommendations`, `recommendation_verdicts`, `surviving_insights`, `recommend_revise_count` → `recommendation`, `recommendation_verdicts`, `recommendation_instances`, `recommend_revise_count`, `stopped` |
| single-inquiry | sign-off | human approval gate (`on_refusal: pause`), tool `record-decision` records it | Stage-Gate go/no-go; may auto-permit by trust-tier policy. | `[entailed_recommendations, recommendations]`, `sign_off_verdict`, `approver`, `trust_basis` → `recommendation`, `decided` |
| single-inquiry | decompose-to-work | process-call (`methodology_ref: conformance-convergence`), tool `decompose-to-work` | Hands signed-off recommendations to conformance-convergence to become work packages. | `[entailed_recommendations, recommendations]`, `surviving_insights`, `signed_off` → `work_package` |
| recursive-inquiry | decompose | tool (`decompose-brief`) | Splits the brief into sub-briefs within the root brief's scope. | `[framed_question, brief]`, `[root_brief, brief]` → `sub_briefs` |
| recursive-inquiry | gather-analyse-ground | process-call per sub-brief (each "is itself a grounded-inquiry"); tool `grounded-recon` bound | Map: one nested grounded-inquiry per sub-brief; merge findings. | `sub_briefs` → `findings` (append) |
| recursive-inquiry | synthesise | tool (`synthesise`) | Reduce findings into candidate claims. | `findings` → `hypothesis` |
| recursive-inquiry | interrogate … decompose-to-work | as single-inquiry | Same steps; `interrogate.revised` returns to `synthesise`. | as above |

## Routes as declared
- Framing: always runs before the entry decision (`framing` block; wiring `frame → classify` declared only in executor, `compile.py:596-601`).
- Entry decision: branch `single-inquiry` (atomic) / `recursive-inquiry` (decomposes). Depth override: when `depth >= max_depth` the non-recursive path is forced — declared only in executor, `max_depth = 4` (`executor/domain/guards.py:24-26`, `compile.py:124-134`). An unrecognised classifier answer becomes `single-inquiry` — declared only in executor (`nodes_prose.py:114`).
- single-inquiry: `start: gather-analyse-ground` → interrogate.
  - `interrogate.gate.on_verdict`: `survived → converge-confidence`, `dropped → end`, `revised → gather-analyse-ground`. Batch verdict = revised if any claim revised and budget left, else survived if any survived, else dropped — declared only in executor (`interrogate.py:90-103`). Budget: counter `revise_count` (+1 per revised batch), loop taken while `revise_count <= MAX_REVISE = 2` → at most 2 loops — declared only in executor (`guards.py:18`).
  - `converge-confidence` → `next: [conclude]`. On `confidence_verdict == insufficient` → honest stop: declared in definition only as prose/preconditions (spec §7 MUST); route declared only in executor (`compile.py:198-206`).
  - `conclude` → recommend → (approval gate) → check-recommendation-fidelity.
  - `recommend.approval_gate`: `permit` → next; anything else → `on_refusal: halt`. Auto-resolution: never `permit` while insufficient; explicit human approval keyed `grounded-inquiry:recommend`; else trust tier ≥ threshold; no threshold declared → `indeterminate` — declared only in executor (`domain/authorization.py:36-131`).
  - `check-recommendation-fidelity.gate.on_verdict`: `entailed → sign-off`, `dropped → end`, `revised → recommend`. Counter `recommend_revise_count`, budget `MAX_RECOMMEND_REVISE = 2` — declared only in executor (`guards.py:19`, `recommendation_fidelity.py:146-164`).
  - `sign-off.approval_gate`: `permit` → decompose-to-work; otherwise `on_refusal: pause` (wait for a person). `on_fail` prose: deny/indeterminate routes back to gather-analyse-ground / interrogate. Precondition: confidence grounded or partial. Nested runs auto-permit (`auto_sign_off=True`) — declared only in executor (`dispatch.py:120`, `nodes_code.py:92-100`).
  - `decompose-to-work` → call `conformance-convergence` → `next: [end]`.
- recursive-inquiry (`recursive: true`): `start: decompose` → gather-analyse-ground (for-each nested grounded-inquiry, depth+1) → synthesise → interrogate (`revised → synthesise`, same counter/budget) → same tail as single.
  - `terminates_when`: every sub-inquiry grounded AND every insight survived AND recommendations signed off, OR `confidence_verdict == insufficient`. Spec §7: evaluate at `end`; if false re-enter `start`. Evaluated only in a test helper, not in routing (`guards.py:29-39`).
- Terminal names (executor `stopped` values): `stopped:insufficient`, `stopped:recommend-indeterminate`, `stopped:no-go`; normal `end`. Definition names none (UNSTATED).

## Scenarios
### S1 — Atomic question, fully approved
- Inputs: `brief` = "Why do panel completes drop on mobile in the UK?"; host `topology_index`; `subject_trust_tier` meets threshold for `grounded-inquiry:recommend`
- Scripted: framing → framed; entry → single-inquiry; gather → 4 findings; interrogate → [survived, survived, dropped]; converge → grounded; conclude → text; recommend gate → permit (auto by policy); fidelity → [entailed, entailed]; sign-off → pause → person approves; decompose-to-work → call:conformance-convergence → end
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [recommend: permit (policy), sign-off: paused → permit (human)]
- Expect terminal: end

### S2 — Every claim refuted
- Inputs: as S1
- Scripted: interrogate → [dropped, dropped]
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate]
- Expect gates: []
- Expect terminal: end (dropped; no conclusion produced)

### S3 — Revise loop taken once
- Inputs: as S1
- Scripted: interrogate#1 → [revised, survived]; gather#2 → findings; interrogate#2 → [survived]; rest as S1
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [recommend: permit (policy), sign-off: permit (human)]
- Expect terminal: end

### S4 — Revise budget exhausted
- Inputs: as S1
- Scripted: interrogate#1,#2,#3 → [revised, survived] each (revise_count 1,2,3); third batch routes survived; rest as S1
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, gather-analyse-ground, interrogate, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [recommend: permit (policy), sign-off: permit (human)]
- Expect terminal: end (a third revised batch with no survivor would instead end as dropped)

### S5 — Evidence insufficient: honest stop
- Inputs: as S1
- Scripted: interrogate → [survived]; converge → insufficient
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence]
- Expect gates: []
- Expect terminal: stopped:insufficient

### S6 — Recommend not licensed, run halts
- Inputs: as S1 but no threshold declared and no human approval recorded
- Scripted: …converge → partial; conclude → text; recommend gate → indeterminate
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend]
- Expect gates: [recommend: indeterminate → halt]
- Expect terminal: stopped:recommend-indeterminate

### S7 — Recommend licensed by recorded human approval
- Inputs: as S6 plus `human_approvals = {"grounded-inquiry:recommend": "user:ana"}`
- Scripted: as S1 from recommend on
- Expect visited: as S1
- Expect gates: [recommend: permit (human user:ana), sign-off: permit (human)]
- Expect terminal: end

### S8 — Fidelity revise taken once
- Inputs: as S1
- Scripted: fidelity#1 → [revised]; recommend#2 → gate permit; fidelity#2 → [entailed]; sign-off approve
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [recommend: permit, recommend: permit, sign-off: permit (human)]
- Expect terminal: end

### S9 — Fidelity revise budget exhausted, all drifted
- Inputs: as S1
- Scripted: fidelity#1,#2 → [revised]; fidelity#3 → [revised] (recommend_revise_count 3, no entailed)
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, recommend, check-recommendation-fidelity, recommend, check-recommendation-fidelity]
- Expect gates: [recommend: permit ×3]
- Expect terminal: end (dropped)

### S10 — Person rejects at sign-off
- Inputs: as S1
- Scripted: sign-off → pause → person denies
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off]
- Expect gates: [recommend: permit, sign-off: paused → deny]
- Expect terminal: stopped:no-go (executor). Definition's on_fail prose would instead re-enter gather-analyse-ground with no budget — see ambiguities.

### S11 — Nested run: sign-off auto-permitted
- Inputs: as S1, run seeded as nested (`auto_sign_off = true`, `depth = 1`), threshold met for recommend
- Scripted: as S1 up to sign-off; sign-off → permit without pause
- Expect visited: as S1
- Expect gates: [recommend: permit (policy), sign-off: permit (auto, executor subject)]
- Expect terminal: end

### S12 — Broad question fans out
- Inputs: `brief` = "What should our 2027 data-quality strategy be?"; threshold met
- Scripted: entry → recursive-inquiry; decompose → [sub-a, sub-b]; each nested run: `call:grounded-inquiry(single-inquiry)→end`; synthesise → 3 hypotheses; interrogate → survived; converge → partial; conclude; recommend permit; fidelity entailed; sign-off approve
- Expect visited: [framing, entry_decision, decompose, `call:grounded-inquiry(single-inquiry)→end` ×2, synthesise, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [nested recommend ×2: permit, nested sign-off ×2: auto-permit, recommend: permit, sign-off: permit (human)]
- Expect terminal: end

### S13 — Recursive revise returns to synthesise
- Inputs: as S12
- Scripted: interrogate#1 → [revised, survived]; synthesise#2; interrogate#2 → [survived]; rest as S12
- Expect visited: [framing, entry_decision, decompose, `call:grounded-inquiry(single-inquiry)→end` ×2, synthesise, interrogate, synthesise, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: as S12
- Expect terminal: end

### S14 — Depth limit forces the atomic path
- Inputs: nested seed `depth = 4`, `max_depth = 4`, `brief` = a broad sub-question
- Scripted: entry classifier → recursive-inquiry (overridden); rest as S11
- Expect visited: [framing, entry_decision, gather-analyse-ground, interrogate, converge-confidence, conclude, recommend, check-recommendation-fidelity, sign-off, decompose-to-work, `call:conformance-convergence(entry-decided)→end`]
- Expect gates: [recommend: permit, sign-off: auto-permit]
- Expect terminal: end (declared only in executor)

### S15 — Recursive path ends without meeting terminates_when
- Inputs: as S12
- Scripted: interrogate → [dropped, dropped]
- Expect visited: [framing, entry_decision, decompose, `call:grounded-inquiry(single-inquiry)→end` ×2, synthesise, interrogate, decompose, …]
- Expect gates: []
- Expect terminal: UNSTATED — spec §7 re-enters `decompose` because the predicate is false, bounded only by depth; executor ends at `end`

## Ambiguities for the process owner
- The insufficient stop is declared only in prose (step preconditions, `terminates_when`); the route is declared only in executor (`compile.py:198-206`). No step declares it as an edge.
- Revise budgets (`MAX_REVISE = 2`, `MAX_RECOMMEND_REVISE = 2`), their counters, and the batch rule (any revised beats any survived) are declared only in executor (`guards.py:18-19`, `interrogate.py:90-103`, `recommendation_fidelity.py:146-164`).
- `check-recommendation-fidelity` routes on `entailed/dropped/revised`, but the schema and spec §5 close the gate vocabulary to `survived/dropped/revised`; its own `gate.verdict` field says `survived`.
- `sign-off` declares `on_refusal: pause`, while its `on_fail` prose says deny/indeterminate route back to gather-analyse-ground (single) or decompose/gather/interrogate (recursive). The executor stops with `no-go`. Loop target and budget for a send-back are unstated (S10).
- `recommend` gate evaluation, the policy order, and "no threshold → indeterminate" are declared only in executor (`domain/authorization.py:36-131`). No threshold value exists in the register, so an unattended run always halts at `recommend` (S6).
- Nested runs auto-permit sign-off (`dispatch.py:120`), so a child's human gate never reaches a person (UC-CALL-GATES).
- `decompose-to-work` declares `methodology_ref: conformance-convergence`, but the executor only mints work packages labelled with that process; no call is made, and there is no input mapping from a recommendation to the callee's required `contract_ref`/`target_form`.
- Recursive `gather-analyse-ground` binds `grounded-recon` (one call) while its action says each sub-inquiry is itself a grounded-inquiry; the executor runs nested processes. Which is the contract is unstated; merge (join) policy for the fan-out is unstated beyond spec §8 append.
- `terminates_when` for `recursive-inquiry` is not evaluated by the executor; spec §7 re-entry (S15) has no declared bound other than the depth bound.
- Single-path `interrogate.dropped → end` skips `conclude`, whose own `on_fail` says a conclusion stating the evidence does not support an answer must still be produced.
- Framing → entry order, the depth override to the non-recursive path, and the default-to-single classifier fallback are declared only in executor.
- `topology_index` and `root_brief` are read but not declared inputs (UC-IN-AMBIENT).
