# classify-candidate — brain

Source: plugins/sulis-brain/instances/classify-candidate/workflow.jsonld
Purpose: Return a reuse-vs-mint verdict for a candidate by applying the four-layer decomposition (L4 render, L3 defer, L2 convention, L1 mint).
Use cases: UC-IN-TYPED, UC-OUT-TYPED, UC-STOP-NAMED, UC-FAILURE-MODES, UC-CRITICALITY, UC-MECHANISM, UC-TRIGGER, UC-CALL

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| assess-layers | probabilistic | Walk Q1 L4 → Q2 L3 → Q3 L2 → Q4 L1 in order on `candidate` → `layer-assessment` | — (content node, no tool) |
| classify-verdict | probabilistic | Apply fixed map L4→propose-renderer, L3→defer-runtime, L2→propose-convention, L1→proceed-to-mint → `reuse-vs-mint-verdict` | — (content node, no tool) |

## Routes as declared
- `assess-layers -> classify-verdict [the four diagnostic questions (L4 -> L3 -> L2 -> L1) were walked in order and the candidate is routed into exactly one layer — layer-assessment exists and can be turned into a verdict]`
  → unconditional sequence (postcondition check on `layer-assessment` present).
- `classify-verdict -> [terminal:classified] [the reuse-vs-mint verdict (layer L1/L2/L3/L4 + routing proceed-to-mint | propose-convention | defer-runtime | propose-renderer) is emitted as reuse-vs-mint-verdict — the candidate is classified]`
  → terminal verdict `classified`.
- Failure modes (no routes_to): `misclassified-layer` (manual-review, non-blocking) → re-walk assess-layers, route UNSTATED; `mint-bias-default-not-reuse` (escalate, non-blocking) → restart assess-layers from Q1, route UNSTATED.

## Scenarios
### S1 — generated artifact (L4)
- Inputs: `candidate: "a YAML file the engine consumes, rendered from workflow entities"`
- Scripted: assess-layers → `{layer: L4}`; classify-verdict → `{layer_verdict: L4, routing_decision: propose-renderer}`
- Expect visited: [assess-layers, classify-verdict]
- Expect gates: []
- Expect terminal: classified

### S2 — runtime occurrence (L3)
- Inputs: `candidate: "a record that step X ran at time T"`
- Scripted: assess-layers → `{layer: L3}`; classify-verdict → `defer-runtime`
- Expect visited: [assess-layers, classify-verdict]
- Expect gates: []
- Expect terminal: classified

### S3 — convention (L2)
- Inputs: `candidate: "the standard retry backoff used everywhere"`
- Scripted: assess-layers → `{layer: L2}`; classify-verdict → `propose-convention`
- Expect visited: [assess-layers, classify-verdict]
- Expect gates: []
- Expect terminal: classified

### S4 — canonical entity (L1)
- Inputs: `candidate: "a per-business pricing plan that tools validate and query"`
- Scripted: assess-layers → `{layer: L1}` (L4, L3, L2 each answered no); classify-verdict → `proceed-to-mint`
- Expect visited: [assess-layers, classify-verdict]
- Expect gates: []
- Expect terminal: classified

### S5 — mint bias caught (failure mode)
- Inputs: `candidate: "an audit report of the brain"`
- Scripted: assess-layers pass 1 → L1 without clearing L4; `mint-bias-default-not-reuse` fires → restart from Q1; pass 2 → L4; classify-verdict → propose-renderer
- Expect visited: [assess-layers, assess-layers, classify-verdict]  (best reading; no declared self-route)
- Expect gates: [escalation notice (non-blocking)]
- Expect terminal: classified

## Ambiguities for the process owner
- The two failure modes describe re-walking assess-layers but declare no route or budget; `misclassified-layer` is handled by classify-verdict too, where a re-walk means going back to the previous step.
- `mint-bias-default-not-reuse` recovery is escalate yet `blocks_progress: false` — whether the run waits is unstated.
- No human step exists, so "manual-review" recovery has no gate to land on.
- `terminal_steps` lists both `classify-verdict` and `[terminal:classified]`.
- The output shape of `reuse-vs-mint-verdict` is prose only (state contract says `dict`); a parent (architect) reads it per candidate but the workflow classifies exactly one `candidate`.
- The L1 "if no → re-route (most likely L3)" in Q4 is a hidden branch inside the step with no declared outcome.
