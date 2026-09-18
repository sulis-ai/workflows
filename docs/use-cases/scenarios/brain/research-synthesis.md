# research-synthesis — brain

Source: plugins/sulis-brain/instances/research-synthesis/workflow.jsonld
Purpose: Gather evidence from external sources, rate its credibility, triangulate and preserve contradictions (both through ooda-spiral), write an SCQA-framed synthesis, get three lens sign-offs, and extract reusable knowledge.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-DECIDE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-VERDICT-ROUTE, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-STOP-NAMED, UC-STOP-HONEST, UC-CALL, UC-CALL-NESTING, UC-CALL-GATES, UC-FOREACH, UC-JOIN, UC-LENS-TRIAD, UC-SPIRAL, UC-GATE-KINDS, UC-GATE-ROUTE, UC-FAILURE-MODES, UC-COMPENSATE, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| scope-frame | mixed | Captures brief slots, frames in/out of scope, detects competitive profile → `scope-frame`, `final-verdict` | none |
| evidence-gather | mixed | Inventories ≥3 sources with coverage categories; targeted re-gather on a cycle back → `source-inventory`, `final-verdict` | none |
| credibility-assess | mixed | Tier 1–4 per source, bias, limitations → `credibility-assessments`, `tier-distribution` | none |
| triangulate | probabilistic | Cross-source coherence claim → `triangulation-result`, `triangulation-ooda-verdict` | triangulate-via-ooda-spiral (workflow_dispatch → **ooda-spiral** `dna:workflow:01KT3SPRXWFNN5VJBSKNX8YGKS`, wait for completion) |
| surface-contradictions | probabilistic | Attacks each side of each contradiction; preserves, never averages → `contradiction-set`, `contradiction-ooda-verdict` | surface-contradictions-via-ooda-spiral (workflow_dispatch → **ooda-spiral**, wait; one child run per divergence point) |
| synthesise | probabilistic | Writes RESEARCH_SYNTHESIS.md (or COMPETITIVE_LANDSCAPE.md) with SCQA → `synthesis-draft`, `scqa-framing`, `research-synthesis-md-ref`, `escalation-recommendation?` | none |
| lens-sign-off | mixed | Three independent lens reviews (evidence-gatherer, source-critic, coherence-analyst) each PROCEED / BLOCK / ESCALATE → `lens-sign-off-record`, `final-verdict` | none |
| knowledge-extract | deterministic | Writes knowledge notes to product/knowledge/ or NO_KNOWLEDGE_EXTRACTED.md → `knowledge-extraction-record`, `final-verdict` | none |

Fan-out and joins:
- `surface-contradictions` fans out: the tool text says one parent run may dispatch ooda-spiral N times, one per divergence point, as sibling child runs. The results must be joined into one `contradiction-set` and one `contradiction-ooda-verdict`; the join policy is not declared.
- `lens-sign-off` holds three independent reviews inside one step (a lens triad), with a composite rule "all PROCEED / any BLOCK / any ESCALATE". Not declared as parallel steps.
- No parallel starts: one initial step.

## Routes as declared
- `scope-frame -> evidence-gather` → unconditional (default).
- `scope-frame -> [terminal:escalated] [if scope-too-broad-to-bound FailureMode unresolved after compensate]` → condition on a failure-mode outcome, no state key → terminal verdict `escalated`.
- `evidence-gather -> credibility-assess` → unconditional (default).
- `evidence-gather -> [terminal:blocked] [if tier-1-empty FailureMode escalates — no peer-reviewed/official-data evidence exists]` → condition on a failure-mode outcome (person chooses narrow / defer / blocked; autonomous default blocked) → terminal verdict `blocked`.
- `credibility-assess -> triangulate` → unconditional (default).
- `credibility-assess -> credibility-assess [if credibility-tier-misclassified FailureMode cycles — re-assess Source Critic verdicts]` → self-loop; budget UNSTATED.
- `triangulate -> surface-contradictions [if triangulation-ooda-verdict in (converged, lean-complete)]` → condition on `triangulation-ooda-verdict`.
- `triangulate -> evidence-gather [if triangulation-ooda-verdict == pass-cap-residual-uncertainty AND residual-uncertainty names a gather-able evidence gap — CYCLE BACK]` → loop on `triangulation-ooda-verdict` plus a judgement ("gather-able") not in state; budget UNSTATED.
- `surface-contradictions -> synthesise [if contradiction-set complete AND contradiction-ooda-verdict != pass-cap-residual-uncertainty without recourse]` → condition on `contradiction-ooda-verdict` plus prose ("complete", "without recourse").
- `surface-contradictions -> evidence-gather [if a contradiction reveals an under-sourced claim — CYCLE BACK targeted re-gather]` → loop on a judgement (postcondition sets `source-inventory.targeted-claim`); budget UNSTATED.
- `synthesise -> lens-sign-off [if synthesis-draft drafted + SCQA framing present]` → condition on presence of `synthesis-draft`, `scqa-framing`.
- `synthesise -> triangulate [if synthesise-without-coherence FailureMode fires — coherence-lens rejects synthesis; re-triangulate]` → loop; the failure mode states the only budget in this process: "if the same synthesise-triangulate cycle fires twice without resolution, route to terminal-escalated" (no transition for it).
- `lens-sign-off -> knowledge-extract [if all three lens verdicts == PROCEED]` → condition on `lens-sign-off-record[*].verdict`.
- `lens-sign-off -> synthesise [if any lens verdict == BLOCK with revision-actionable concerns — CYCLE BACK to re-draft]` → loop on the same; budget UNSTATED.
- `lens-sign-off -> [terminal:escalated] [if any lens verdict == ESCALATE — foundational issue surfaced; SCQA names the bigger problem]` → terminal verdict `escalated`.
- `knowledge-extract -> [terminal:synthesised] [if patterns/findings/proof-points emitted OR explicit NO_KNOWLEDGE_EXTRACTED rationale recorded]` → terminal verdict `synthesised`.

## Scenarios
### S1 — Happy path
- Inputs: `research-brief = {topic: "pricing models for developer tools", scope: "2022–2026, industry + academic", decision-context: "choose pricing for launch", stakeholders: ["founder"]}`
- Scripted: scope-frame → standard profile; evidence-gather → 7 sources; credibility-assess → tiers; ooda-spiral (triangulate) → converged; ooda-spiral (1 contradiction) → converged; synthesise → draft + SCQA; lens-sign-off → PROCEED ×3; knowledge-extract → 2 patterns
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S2 — Scope cannot be bounded
- Inputs: `research-brief = {topic: "tell me about AI"}`
- Scripted: scope-frame → compensate (ask four slot questions) → person cannot narrow
- Expect visited: [scope-frame]
- Expect gates: [scope slot questions → no usable answer]
- Expect terminal: escalated

### S3 — No Tier 1 evidence
- Inputs: brief on an emerging topic
- Scripted: evidence-gather → only tier-2 sources for the load-bearing claim; tier-1-empty → person chooses "treat as blocked" (autonomous default)
- Expect visited: [scope-frame, evidence-gather]
- Expect gates: [tier-1-empty → blocked]
- Expect terminal: blocked

### S4 — Credibility re-assessed once
- Inputs: as S1
- Scripted: credibility-assess pass 1 → tier-misclassified raised; pass 2 → settled
- Expect visited: [scope-frame, evidence-gather, credibility-assess, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S5 — Triangulation hits pass cap with a gather-able gap
- Inputs: as S1
- Scripted: triangulate pass 1 → ooda-spiral pass-cap-residual-uncertainty naming a gap; evidence-gather (targeted); credibility-assess; triangulate pass 2 → converged; rest as S1
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→pass-cap-residual-uncertainty, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S6 — Contradiction reveals an under-sourced claim
- Inputs: as S1
- Scripted: surface-contradictions → ooda-spiral → under-evidenced, gap gather-able; targeted re-gather; second pass converged
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S7 — Several contradictions, fan-out and join
- Inputs: as S1, triangulation finds 3 divergence points
- Scripted: surface-contradictions dispatches 3 child runs → converged, converged, pass-cap-residual-uncertainty (genuine contradiction, preserved; contradictions-unresolved is manual-review but non-blocking)
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, {call:ooda-spiral→converged, call:ooda-spiral→converged, call:ooda-spiral→pass-cap-residual-uncertainty} (parallel or serial, UNSTATED), synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised (contradictions preserved in the document)

### S8 — Synthesis lacks coherence, re-triangulate once
- Inputs: as S1
- Scripted: synthesise → synthesise-without-coherence; triangulate → converged (tighter claim); surface-contradictions → converged; synthesise → ok
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S9 — Synthesise ↔ triangulate cycle exhausted
- Inputs: as S1
- Scripted: synthesise-without-coherence fires twice without resolution
- Expect visited: [scope-frame, evidence-gather, credibility-assess] + 3 × [triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise]
- Expect gates: []
- Expect terminal: escalated (stated in failure-mode prose only)

### S10 — A lens blocks, re-draft, then all proceed
- Inputs: as S1
- Scripted: lens-sign-off pass 1 → source-critic BLOCK with revision actions; synthesise → re-draft; lens-sign-off pass 2 → PROCEED ×3
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off, synthesise, lens-sign-off, knowledge-extract]
- Expect gates: []
- Expect terminal: synthesised

### S11 — A lens escalates
- Inputs: as S1
- Scripted: lens-sign-off → coherence-analyst ESCALATE
- Expect visited: [scope-frame, evidence-gather, credibility-assess, triangulate, call:ooda-spiral→converged, surface-contradictions, call:ooda-spiral→converged, synthesise, lens-sign-off]
- Expect gates: []
- Expect terminal: escalated

### S12 — Loops with no stated budget, exhausted
One scenario per unbudgeted loop; each should be refused by a validator or given a budget by the owner.
- S12a credibility-assess self-loop never settles → Expect terminal: UNSTATED
- S12b triangulate → evidence-gather keeps returning pass-cap with gather-able gap → Expect terminal: UNSTATED
- S12c surface-contradictions → evidence-gather keeps finding under-sourced claims → Expect terminal: UNSTATED
- S12d lens-sign-off → synthesise, a lens BLOCKs every pass → Expect terminal: UNSTATED
- Expect gates: [] for all

### S13 — Nothing extractable
- Inputs: as S1
- Scripted: knowledge-extract → NO_KNOWLEDGE_EXTRACTED.md with rationale
- Expect visited: as S1
- Expect gates: []
- Expect terminal: synthesised

## Ambiguities for the process owner
- Four of five loops have no budget; the fifth (synthesise ↔ triangulate) has one only in failure-mode prose, with no transition to `escalated`.
- Three routes are conditioned on failure-mode outcomes ("FailureMode unresolved", "escalates", "fires"), not on state values.
- "Gather-able", "revision-actionable", "complete", and "without recourse" are judgements with no state key.
- No route from `triangulate` when the verdict is `pass-cap-residual-uncertainty` and the gap is not gather-able; no route from `surface-contradictions` when its verdict is pass-cap "with no recourse". The failure mode synthesise-without-coherence says a pass-cap result should be acknowledged in the synthesis, which suggests a forward route that is not declared.
- The N-way dispatch in surface-contradictions has no declared concurrency, join policy, or rule for combining N child verdicts into one `contradiction-ooda-verdict`.
- Tier-1-empty and scope-too-broad are human decisions (options narrow / defer / blocked; four slot questions) with no gate step. "Defer the decision" has no route or verdict.
- A child ooda-spiral's convergence-faked review must surface to "the parent Workflow's dispatching agent"; how a child's human decision reaches a person is undeclared.
- `final-verdict` is written by four different steps (scope-frame, evidence-gather, lens-sign-off, knowledge-extract); the reducer is unstated.
- `knowledge-extract` is the only terminal step, yet the run can end at scope-frame, evidence-gather and lens-sign-off.
- credibility-tier-misclassified is raised "later in the Workflow" (at triangulate) but the only declared route is a self-loop on credibility-assess, which cannot observe it. Downgrading a source should also invalidate triangulation built on it (compensation) — unstated.
- On the S5/S6 cycle backs, whether credibility-assess and triangulate re-run over the whole inventory or only the new sources is unstated.
