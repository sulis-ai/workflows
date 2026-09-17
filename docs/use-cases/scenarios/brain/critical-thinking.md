# critical-thinking — brain

Source: plugins/sulis-brain/instances/critical-thinking/workflow.jsonld
Purpose: Pressure-test a decision, hypothesis, or strategic question before commitment, lean single-pass or a spiral that composes research-synthesis and ooda-spiral.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-DECIDE, UC-PATHS, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-STOP-HONEST, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-COMPENSATE, UC-CALL, UC-CALL-PATH, UC-FAILURE-MODES, UC-CRITICALITY, UC-MECHANISM, UC-TOOL-KINDS, UC-TRIGGER, UC-SPIRAL

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| complexity-gate | deterministic | Classify request → `complexity-verdict` lean/spiral (forced spiral when parent-dispatched or rigor event) | — |
| scqa-frame | mixed | Situation/Complication/Question/Answer → `scqa-frame` | — |
| evidence-gather | mixed | Lean: inline evidence. Spiral: dispatch research → `evidence-set`, `research-synthesis-verdict?` | dispatch-research-synthesis (workflow_dispatch → `research-synthesis`, dna:workflow:0142RSNTJ45YHJF337QA4PTEX8, wait) — spiral path only |
| apply-principles | probabilistic | Classify question type, apply load-bearing principles → `principles-applied`, `candidate-conclusion` | — |
| run-spiral | mixed | Attack own conclusion → `ooda-spiral-verdict`, revised `candidate-conclusion`, `spiral-trace` | dispatch-ooda-spiral (workflow_dispatch → `ooda-spiral`, dna:workflow:01KT3SPRXWFNN5VJBSKNX8YGKS, wait) |
| anti-pattern-check | deterministic | Scan AP-01..AP-09 + lazy-critical-thinking integrity check → `anti-patterns-detected` | — |
| structured-output | deterministic | Emit CRITICAL_THINKING_ANALYSIS.md with Binding Constraints section → `structured-output-ref`, `final-verdict` | — |

## Routes as declared
- `complexity-gate -> scqa-frame` → unconditional.
- `scqa-frame -> evidence-gather` → unconditional.
- `evidence-gather -> apply-principles` → default (no condition).
- `evidence-gather -> [terminal:scope-misread-escalate] [if research-synthesis-verdict == escalated AND escalation names an out-of-scope foundational issue]` → condition `research-synthesis-verdict == escalated` (second clause UNSTATED in state) → terminal `scope-misread-escalate`.
- `apply-principles -> scqa-frame [if a principle's analysis reframed the question …] [invalidates: principles-applied, candidate-conclusion; PRESERVED: evidence-set …] [max_firings: 2 — … re-re-framing … should escalate via terminal:scope-misread-escalate rather than cycle again]` → loop back to scqa-frame; condition UNSTATED (no "reframed" key); budget 2; invalidates principles-applied, candidate-conclusion; exhaustion → terminal `scope-misread-escalate` (prose).
- `apply-principles -> run-spiral [if complexity-verdict == spiral]` → condition `complexity-verdict == spiral`.
- `apply-principles -> anti-pattern-check [if complexity-verdict == lean — single-pass shortcut: skip run-spiral …]` → condition `complexity-verdict == lean`.
- `run-spiral -> anti-pattern-check [if ooda-spiral-verdict in (converged, lean-complete)]` → condition on `ooda-spiral-verdict`.
- `run-spiral -> evidence-gather [if ooda-spiral-verdict == pass-cap-residual-uncertainty AND residual-uncertainty names a gather-able evidence gap — CYCLE BACK …] [invalidates: principles-applied, candidate-conclusion, spiral-trace; PRESERVED: scqa-frame; evidence-set is REPLACED …] [max_firings: 2 — … surface honest residual-uncertainty in structured-output rather than thrash]` → loop back; condition `ooda-spiral-verdict == pass-cap-residual-uncertainty` + UNSTATED "gather-able" flag; budget 2; evidence-set reducer replace; exhaustion → proceed to structured-output with residual (prose; no declared edge).
- `anti-pattern-check -> structured-output [if anti-patterns-detected.unresolved == 0]` → condition `anti-patterns-detected.unresolved == 0`.
- `anti-pattern-check -> apply-principles [if an anti-pattern was detected AND the producing-phase is apply-principles or earlier — CYCLE BACK …] [invalidates: candidate-conclusion, spiral-trace? …; principles-applied is REVISED …] [max_firings: 3 — … If the same anti-pattern (by ap-id) fires twice across the bound, … route to terminal:scope-misread-escalate]` → loop back; condition `unresolved > 0 AND producing-phase ∈ {apply-principles, evidence-gather, scqa-frame}`; budget 3; exhaustion → terminal `scope-misread-escalate`.
- `anti-pattern-check -> [terminal:scope-misread-escalate] [if lazy-critical-thinking FailureMode fires AND recovery=abort triggers …]` → failure-mode-driven terminal `scope-misread-escalate`.
- `structured-output -> [terminal:lean-complete] [if complexity-verdict == lean AND final output produced]` → terminal.
- `structured-output -> [terminal:spiral-converged] [if complexity-verdict == spiral AND ooda-spiral-verdict == converged AND anti-patterns-detected.unresolved == 0]` → terminal.
- `structured-output -> [terminal:spiral-pass-cap-residual] [if complexity-verdict == spiral AND ooda-spiral-verdict == pass-cap-residual-uncertainty]` → terminal.

## Scenarios
### S1 — lean single pass
- Inputs: `request: {text: "poke holes in this assumption: users want CSV export"}`
- Scripted: complexity-gate → lean; evidence-gather → inline set; apply-principles → conclusion; anti-pattern-check → unresolved 0; structured-output → file
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: lean-complete

### S2 — spiral converged
- Inputs: `request: {text: "should we enter market X? be rigorous"}`
- Scripted: complexity-gate → spiral; research-synthesis → `synthesised`; ooda-spiral → `converged`; anti-pattern-check → 0
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→converged], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-converged

### S3 — parent-dispatched run forces spiral
- Inputs: `request: {text: "is this assumption sound?"}`, triggered by `parent-workflow-dispatched`
- Scripted: complexity-gate → spiral (forced despite lean-shaped text); rest as S2
- Expect visited: as S2
- Expect gates: []
- Expect terminal: spiral-converged

### S4 — spiral, ooda short-circuits to lean-complete
- Inputs: as S2
- Scripted: ooda-spiral → `lean-complete`; anti-pattern-check → 0
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→lean-complete], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-converged (best reading; no structured-output route matches spiral + lean-complete)

### S5 — pass cap, residual not gather-able
- Inputs: as S2
- Scripted: ooda-spiral → `pass-cap-residual-uncertainty`, residual names no gather-able gap
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→pass-cap-residual-uncertainty], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-pass-cap-residual

### S6 — targeted re-gather once, then converged
- Inputs: as S2
- Scripted: ooda pass 1 → `pass-cap-residual-uncertainty` naming a gather-able gap; research-synthesis (targeted) → `synthesised`; ooda pass 2 → `converged`
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→pass-cap-residual-uncertainty], evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→converged], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-converged

### S7 — targeted re-gather budget exhausted
- Inputs: as S2
- Scripted: every ooda pass → `pass-cap-residual-uncertainty` with a gather-able gap
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→pass-cap-residual-uncertainty], (evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→pass-cap-residual-uncertainty]) ×2, anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-pass-cap-residual

### S8 — research escalates
- Inputs: as S2
- Scripted: research-synthesis → `escalated` (out-of-scope foundational issue)
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→escalated]]
- Expect gates: []
- Expect terminal: scope-misread-escalate

### S9 — research blocked, gap carried forward
- Inputs: as S2
- Scripted: research-synthesis → `blocked` (tier-1 empty); apply-principles surfaces the gap; ooda-spiral → `converged`
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→blocked], apply-principles, run-spiral[call:ooda-spiral→converged], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-converged

### S10 — question reframed once
- Inputs: as S1
- Scripted: apply-principles pass 1 → MECE reveals false dichotomy, reframe; scqa-frame re-emits question; pass 2 → conclusion
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, scqa-frame, evidence-gather, apply-principles, anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: lean-complete

### S11 — reframe budget exhausted
- Inputs: as S1
- Scripted: apply-principles → reframe on every pass
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, scqa-frame, evidence-gather, apply-principles, scqa-frame, evidence-gather, apply-principles]
- Expect gates: []
- Expect terminal: scope-misread-escalate

### S12 — anti-pattern corrected once
- Inputs: as S1
- Scripted: anti-pattern-check pass 1 → AP-07 unresolved 1 (producing-phase apply-principles); apply-principles revises; pass 2 → 0
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, anti-pattern-check, apply-principles, anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: lean-complete

### S13 — anti-pattern loop exhausted
- Inputs: as S1
- Scripted: anti-pattern-check → same AP unresolved on every pass
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, (anti-pattern-check, apply-principles) ×3, anti-pattern-check]  (budget 3; the "same ap-id twice" rule could stop after 2)
- Expect gates: []
- Expect terminal: scope-misread-escalate

### S14 — lazy critical thinking
- Inputs: as S2
- Scripted: ooda-spiral → `converged` but spiral-trace attacks only the user's framing; lazy-critical-thinking fires (abort)
- Expect visited: [complexity-gate, scqa-frame, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→converged], anti-pattern-check]
- Expect gates: []
- Expect terminal: scope-misread-escalate

### S15 — lean promoted to spiral (failure mode research-skipped-but-needed)
- Inputs: as S1
- Scripted: complexity-gate → lean; after apply-principles, research-skipped-but-needed fires (compensate): `complexity-verdict := spiral`, route back to evidence-gather; research-synthesis → `synthesised`; ooda-spiral → `converged`
- Expect visited: [complexity-gate, scqa-frame, evidence-gather, apply-principles, evidence-gather[call:research-synthesis→synthesised], apply-principles, run-spiral[call:ooda-spiral→converged], anti-pattern-check, structured-output]
- Expect gates: []
- Expect terminal: spiral-converged

## Ambiguities for the process owner
- `run-spiral` with `pass-cap-residual-uncertainty` and no gather-able gap has no declared edge (step prose says proceed to anti-pattern-check); the loop's exhaustion edge is likewise prose.
- No structured-output route covers spiral + `ooda-spiral-verdict == lean-complete`, or spiral + converged with unresolved > 0; `terminal:scope-misread-escalate` is reached without passing structured-output, yet lazy-critical-thinking says structured-output emits the escalation file.
- "reframed the question", "gather-able evidence gap", "out-of-scope foundational issue" and "producing-phase is reachable" are judgements with no state key.
- apply-principles → scqa-frame claims evidence-set is PRESERVED, but scqa-frame's only exit re-enters evidence-gather (which re-dispatches research on the spiral path).
- anti-pattern-check has two budget rules (max_firings 3 vs "same ap-id twice"); producing-phase may be run-spiral or evidence-gather, but the only declared correction edge targets apply-principles. The anti-pattern-detected failure mode routes AP-01 to evidence-gather — an undeclared edge.
- Failure modes complexity-misclassified and research-skipped-but-needed promote lean→spiral mid-run by rewriting `complexity-verdict` and routing back; neither route is a declared transition. rebuttal-unexamined (compensate, blocks) has no route.
- `spiral-trace` is written by run-spiral and read by anti-pattern-check but is not in the state contract; `candidate-conclusion (revised)` is an output name with prose in it.
- `ooda-spiral` child is forced to spiral but may short-circuit via `prefer-lean-if-converged-early`; the caller chooses the child's path through a flag, not a declared path selector.
- Parent callers (architect, author-a-discipline) expect verdicts `converged|residual|escalated`, which this workflow does not emit.
