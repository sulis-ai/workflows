# dna-mint-an-entity — brain

Source: plugins/sulis-brain/instances/dna-minting-process/workflow.jsonld
Purpose: End-to-end minting of a new Sulis Brain entity, from identification through classification, admission gates, validation and plugin distribution.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-VERDICT-ROUTE, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-COMPENSATE, UC-CALL, UC-CALL-NESTING, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-RETRY, UC-FAILURE-MODES, UC-CRITICALITY, UC-SIDE-EFFECT-CLAIM, UC-TOOL-KINDS, UC-TOOL-RUNNER, UC-MECHANISM, UC-TRIGGER

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| phase-0-identify | human | Operator describes the candidate → `candidate-spec` | — (input gate) |
| phase-0.5-classify | mixed | Four-layer classification → `layer-verdict`, `routing-decision` | skill `/sulis-brain:classify-candidate` (no tool_ref; the classify-candidate workflow exists) |
| phase-1-convention-scan | mixed | Adopt/extend/deviate against W3C/IETF/ISO conventions → `convention-scan-report` | — |
| phase-1.5-critical-thinking | probabilistic | Pressure-test the framing → `candidate-confidence-verdict` (strong/weak/reject), `critical-thinking-trace-ref` | dispatch-critical-thinking (workflow_dispatch → `critical-thinking`, dna:workflow:01KT1N632VCT1J0XWY7NMVDHCJ, forced spiral) |
| phase-2-discovery-probes | human | Walk 12 probes one per turn → `probe-responses` | — (input gate) |
| phase-2.5-altitude-discovery | human | Altitude test → `altitude-verdict` (mint-here/promote-base/split/merge) | — (input gate) |
| phase-3-pyramid-mapping | human | Confirm domain/altitude/siblings → `pyramid-position` | — (input gate) |
| phase-4-qualitative-admission | human | JT-1..JT-7 by trajectory (4a/4b/4c) → `qualitative-verdict` (admit-draft/reject/reshape) | — (approval gate) |
| phase-4.5-numeric-admission | deterministic | `dna-runner admission` → `numeric-score`, `numeric-verdict` (≥0.85 admit, 0.50–0.85 escalate, <0.50 reject) | CLI via Bash (no tool entity) |
| phase-5-ooda-validation | probabilistic | Self-attack the conclusion → `ooda-verdict`, `residual-uncertainty` | skill `/sulis-brain:critical-thinking` (no tool_ref) |
| phase-5.5-referential-integrity | deterministic | Dangling refs, mirror consistency, MAJOR-bump cascade → `integrity-report`; operator decides remediation | skill `/sulis-brain:check-referential-integrity` |
| phase-5.7-disambiguation-sweep | mixed | Synonym clusters confirmed one per turn → `disambiguation-report`, `glossary-updates` | skill `/sulis-brain:disambiguate-vocabulary` |
| phase-6-outputs | mixed | Author field-spec, `dna-runner compile` + `validate` rubric, DR draft → outputs (rubric-verdict per postcondition) | CLI `dna-runner` |
| phase-7-distribution | deterministic | Sync to plugin, descriptions, narrative docs, commit, push | `sync-from-canonical.sh`, git, release-on-merge |

## Routes as declared
- `phase-0-identify -> phase-0.5-classify` → unconditional.
- `phase-0.5-classify -> phase-1-convention-scan [if layer-verdict == L1]` → condition `layer-verdict == L1`.
- `phase-0.5-classify -> [terminal:propose-convention] [if L2 — abort minting]` → `layer-verdict == L2` → terminal `propose-convention`.
- `phase-0.5-classify -> [terminal:defer-runtime] [if L3 — abort minting]` → `== L3` → terminal `defer-runtime`.
- `phase-0.5-classify -> [terminal:propose-renderer] [if L4 — abort minting]` → `== L4` → terminal `propose-renderer`.
- `phase-1-convention-scan -> phase-1.5-critical-thinking [if convention-scan-verdict in (aligned, aligned-with-deviation) — proceed to framing pressure-test]` → condition on `convention-scan-verdict` (key not in state contract).
- `phase-1-convention-scan -> phase-1.5-critical-thinking [if convention-scan-verdict == mismatched — …]` → same target; together effectively unconditional.
- `phase-1.5-critical-thinking -> phase-2-discovery-probes [if candidate-confidence-verdict == strong]` → condition.
- `phase-1.5-critical-thinking -> phase-2-discovery-probes [if candidate-confidence-verdict == weak — proceed with warning; …]` → condition (same target).
- `phase-1.5-critical-thinking -> [terminal:candidate-framing-rejected] [if candidate-confidence-verdict == reject — abort the walk; …]` → terminal `candidate-framing-rejected`.
- `phase-2-discovery-probes -> phase-2.5-altitude-discovery` → unconditional.
- `phase-2.5-altitude-discovery -> phase-3-pyramid-mapping` → unconditional (all four `altitude-verdict` values continue).
- `phase-3-pyramid-mapping -> phase-4-qualitative-admission` → unconditional.
- `phase-4-qualitative-admission -> phase-4.5-numeric-admission [if verdict=admit-draft]` → `qualitative-verdict == admit-draft`.
- `phase-4-qualitative-admission -> phase-1-convention-scan [if verdict=reshape — CYCLE BACK on JT insufficient or convention miss]` → loop to phase-1; budget UNSTATED.
- `phase-4-qualitative-admission -> [terminal:reject-jt-fail] [if verdict=reject]` → terminal `reject-jt-fail`.
- `phase-4.5-numeric-admission -> phase-5-ooda-validation [if numeric-verdict=admit]` → condition.
- `phase-4.5-numeric-admission -> phase-4-qualitative-admission [if numeric-verdict=escalate — CYCLE back to operator review]` → loop (send back to a person); budget UNSTATED.
- `phase-4.5-numeric-admission -> [terminal:reject-score] [if numeric-verdict=reject]` → terminal `reject-score`.
- `phase-5-ooda-validation -> phase-5.5-referential-integrity [if ooda-verdict=converged]` → condition.
- `phase-5-ooda-validation -> phase-4-qualitative-admission [if attack disconfirms qualitative — CYCLE BACK]` → loop; condition value UNSTATED (not in `ooda-verdict` enum); budget UNSTATED.
- `phase-5-ooda-validation -> phase-1-convention-scan [if attack reveals convention miss — CYCLE FAR BACK]` → loop; condition value UNSTATED; budget UNSTATED.
- `phase-5.5-referential-integrity -> phase-5.7-disambiguation-sweep [if integrity-report clean]` → condition `integrity-report.violations == []`.
- `phase-5.5-referential-integrity -> phase-6-outputs [if violations acknowledged + remediation planned — proceed to fix in field-spec]` → condition on an operator decision (UNSTATED key); skips phase-5.7.
- `phase-5.7-disambiguation-sweep -> phase-6-outputs [if vocabulary locked]` → condition (UNSTATED key).
- `phase-5.7-disambiguation-sweep -> phase-1-convention-scan [if synonym was a missed convention — CYCLE FAR BACK]` → loop; budget UNSTATED.
- `phase-6-outputs -> phase-7-distribution [if rubric-verdict in (PASS, WARN)]` → condition.
- `phase-6-outputs -> phase-6-outputs [if rubric-verdict=FAIL — CYCLE SELF: re-author]` → self-loop; budget 3 (from failure mode rubric-fail), exhaustion → manual review.
- (no transition out of phase-7-distribution) → terminal; verdict name UNSTATED (best reading `admitted`).

## Scenarios
Shorthand: `FRONT` = [phase-0-identify, phase-0.5-classify, phase-1-convention-scan, phase-1.5-critical-thinking[call:critical-thinking→spiral-converged], phase-2-discovery-probes, phase-2.5-altitude-discovery, phase-3-pyramid-mapping, phase-4-qualitative-admission]; `BACK` = [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-5.5-referential-integrity, phase-5.7-disambiguation-sweep, phase-6-outputs, phase-7-distribution]. Human gates in FRONT: phase-0 (input), phase-2 (input), phase-2.5 (input), phase-3 (input), phase-4 (approval).

### S1 — admitted
- Inputs: `mint-request: {description: "a Warranty entity for insurance"}`
- Scripted: phase-0 → spec; classify → L1; scan → aligned; critical-thinking → framing strong; probes answered; altitude mint-here; pyramid set; phase-4 → admit-draft; admission score 0.91 → admit; ooda → converged; integrity clean; vocabulary locked; rubric PASS; distribution done
- Expect visited: FRONT + BACK
- Expect gates: [phase-0-identify, phase-2-discovery-probes, phase-2.5-altitude-discovery, phase-3-pyramid-mapping, phase-4-qualitative-admission(admit-draft), phase-5.5 operator acknowledgement (none needed), phase-5.7 cluster confirmations]
- Expect terminal: admitted (best reading)

### S2 — L2 convention
- Scripted: classify → L2
- Expect visited: [phase-0-identify, phase-0.5-classify]
- Expect gates: [phase-0-identify]
- Expect terminal: propose-convention

### S3 — L3 runtime
- Scripted: classify → L3
- Expect visited: [phase-0-identify, phase-0.5-classify]
- Expect gates: [phase-0-identify]
- Expect terminal: defer-runtime

### S4 — L4 generated artifact
- Scripted: classify → L4
- Expect visited: [phase-0-identify, phase-0.5-classify]
- Expect gates: [phase-0-identify]
- Expect terminal: propose-renderer

### S5 — framing rejected
- Scripted: classify L1; critical-thinking → reject
- Expect visited: [phase-0-identify, phase-0.5-classify, phase-1-convention-scan, phase-1.5-critical-thinking[call:critical-thinking→scope-misread-escalate]]
- Expect gates: [phase-0-identify]
- Expect terminal: candidate-framing-rejected

### S6 — convention mismatched, weak framing, still admitted
- Scripted: scan → mismatched; critical-thinking → weak; rest as S1
- Expect visited: FRONT (with phase-1.5 → `call:critical-thinking→spiral-pass-cap-residual`) + BACK
- Expect gates: as S1
- Expect terminal: admitted

### S7 — qualitative reject
- Scripted: phase-4 → reject
- Expect visited: FRONT
- Expect gates: [phase-0, phase-2, phase-2.5, phase-3, phase-4(reject)]
- Expect terminal: reject-jt-fail

### S8 — qualitative reshape once
- Scripted: phase-4 pass 1 → reshape; second walk from phase-1 → admit-draft; rest as S1
- Expect visited: FRONT + [phase-1-convention-scan, phase-1.5-critical-thinking[call:critical-thinking→spiral-converged], phase-2-discovery-probes, phase-2.5-altitude-discovery, phase-3-pyramid-mapping, phase-4-qualitative-admission] + BACK
- Expect gates: FRONT gates, then phase-2, phase-2.5, phase-3, phase-4(admit-draft)
- Expect terminal: admitted

### S9 — numeric reject
- Scripted: phase-4 → admit-draft; score 0.32 → reject
- Expect visited: FRONT + [phase-4.5-numeric-admission]
- Expect gates: FRONT gates
- Expect terminal: reject-score

### S10 — numeric escalate, operator re-review, admitted
- Scripted: score 0.70 → escalate; phase-4 → admit-draft; re-score 0.88 → admit; rest as S1
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-4-qualitative-admission] + BACK
- Expect gates: FRONT gates + phase-4(admit-draft)
- Expect terminal: admitted

### S11 — OODA disconfirms qualitative verdict
- Scripted: phase-5 pass 1 → disconfirms qualitative; phase-4 → admit-draft; 4.5 → admit; phase-5 → converged
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-4-qualitative-admission] + BACK
- Expect gates: FRONT gates + phase-4
- Expect terminal: admitted

### S12 — OODA reveals convention miss
- Scripted: phase-5 pass 1 → convention miss; walk again from phase-1; all pass
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-1-convention-scan, phase-1.5-critical-thinking[call:critical-thinking→spiral-converged], phase-2-discovery-probes, phase-2.5-altitude-discovery, phase-3-pyramid-mapping, phase-4-qualitative-admission] + BACK
- Expect gates: FRONT gates twice
- Expect terminal: admitted

### S13 — integrity violations acknowledged
- Scripted: integrity-report → 2 violations; operator acknowledges with remediation plan
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-5.5-referential-integrity, phase-6-outputs, phase-7-distribution]
- Expect gates: FRONT gates + phase-5.5 operator decision (acknowledge)
- Expect terminal: admitted

### S14 — missed synonym convention
- Scripted: phase-5.7 → synonym was a missed convention; walk again from phase-1; all pass
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-5.5-referential-integrity, phase-5.7-disambiguation-sweep, phase-1-convention-scan, phase-1.5-critical-thinking[call:critical-thinking→spiral-converged], phase-2-discovery-probes, phase-2.5-altitude-discovery, phase-3-pyramid-mapping, phase-4-qualitative-admission] + BACK
- Expect gates: FRONT gates twice + phase-5.7 confirmations
- Expect terminal: admitted

### S15 — rubric fails once
- Scripted: phase-6 pass 1 → FAIL; pass 2 → WARN
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-5.5-referential-integrity, phase-5.7-disambiguation-sweep, phase-6-outputs, phase-6-outputs, phase-7-distribution]
- Expect gates: as S1
- Expect terminal: admitted

### S16 — rubric retries exhausted
- Scripted: phase-6 → FAIL on every pass
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation, phase-5.5-referential-integrity, phase-5.7-disambiguation-sweep, phase-6-outputs, phase-6-outputs, phase-6-outputs, phase-6-outputs]  (initial + 3 retries)
- Expect gates: as S1 + manual review of the rubric failure
- Expect terminal: none — halted awaiting manual review (no route declared)

### S17 — OODA residual uncertainty
- Scripted: phase-5 → `residual-uncertainty` (pass cap 4)
- Expect visited: FRONT + [phase-4.5-numeric-admission, phase-5-ooda-validation]
- Expect gates: FRONT gates
- Expect terminal: UNSTATED (no route for `ooda-verdict == residual-uncertainty`)

## Ambiguities for the process owner
- Terminal names do not match `final-outcome: enum[admitted|reshaped|rejected|routed-elsewhere|framing-rejected]`: the declared terminals are `propose-convention`, `defer-runtime`, `propose-renderer`, `candidate-framing-rejected`, `reject-jt-fail`, `reject-score`; phase-7 has no named verdict.
- No budget on any of the five backward loops (phase-4→1, 4.5→4, 5→4, 5→1, 5.7→1); only the phase-6 self-loop has one (3, in a failure mode, exhaustion to manual review with no route).
- `ooda-verdict == residual-uncertainty` has no route; the two disconfirm routes read values not in the enum. The ooda-attack-disconfirms failure mode says "continue forward when … pass cap (4) hit", contradicting the missing route.
- `convention-scan-verdict` and `rubric-verdict` are routed on but no step lists them as outputs (`convention-scan-verdict` is not in the state contract); both convention-scan routes go to the same step.
- phase-5.5 with violations that are neither clean nor acknowledged (operator aborts) has no route; the acknowledged route skips phase-5.7 entirely.
- phase-0.5 and phase-5 call classify-candidate and critical-thinking as skills with no tool_ref, while phase-1.5 dispatches the same critical-thinking workflow via a tool — the same child is called two different ways. critical-thinking's verdicts (`spiral-converged`, …) do not map to `strong|weak|reject` or `converged|residual-uncertainty`.
- Several steps shell out (`dna-runner`, `sync-from-canonical.sh`, git push) with no tool entity; phase-7 has irreversible side effects (commit, push, release) with no precondition or claim.
- phase-4's JT gate is an approval whose three decisions are routed, but the reshape/escalate send-backs carry no note field and no redo budget.
- Inputs `all-entity-artifacts`, `all-prior-phase-outputs`, `authored-artifacts` are not in the state contract (ambient reads).
- Failure modes jt-routing-required, duplicate-detected, convention-deviation-unjustified, non-L1-classification describe routes (enhance-existing flow, default to adopt) that are not transitions.
