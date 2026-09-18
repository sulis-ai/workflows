# methodology-change — methodology sequence

Source: methodology/sequences/methodology-change/DAG.yaml (v3.0.0), methodology/sequences/methodology-change/HANDOFF_CONTRACT.yaml (v2.0.0), methodology/sequences/methodology-change/SEQUENCE.md (v4.x)
Purpose: Classify a proposed methodology change as tactical or significant and run either a one-outcome linear implementation or a six-outcome gated pipeline, always ending with decision recording and documentation sync in parallel.
Use cases: UC-SEQUENCE, UC-EXEC-POLICY, UC-PREPHASE, UC-DECIDE, UC-PATHS, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-HANDOFF, UC-OUT-MULTI, UC-PARALLEL, UC-JOIN, UC-CRITICALITY, UC-PRECONDITION, UC-STOP-NAMED

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| scope-capture | step (`scope_capture`) | Gather inputs; record sha256 checksums of targeted artifacts (SEQUENCE.md) | — → `inputs/recorded_checksums.json` | UNSTATED |
| classify-change | routing (`router`) | Apply TC-01..TC-05 ALL-of; default significant | scope-capture → classification + per-criterion rationale | UNSTATED |
| outcome-research-synthesis | outcome | Evidence + triad synthesis (path significant) | classify-change → RESEARCH_SYNTHESIS.md, RECOMMENDATION.md, lenses/*/ANALYSIS.md | standard |
| outcome-options-analysis | outcome | Compare ≥2 approaches | research-synthesis → OPTIONS_ANALYSIS.md, lenses/*/ANALYSIS.md | standard |
| gate-01 | gate | Research + Options Approval | options-analysis → decision | critical |
| outcome-methodology-evolution | outcome | Triad lens evaluation | gate-01 → EVOLUTION_PROPOSAL.md, TENSION_REPORT.md, lenses/*/ANALYSIS.md | standard |
| outcome-stress-testing | outcome | Adversarial validation, ≥2 ARC cycles | methodology-evolution → STRESS_TEST_REPORT.md, arc/ARC_RESULTS.md | standard |
| outcome-execution-readiness | outcome | Verify comprehension + prerequisites | stress-testing → READINESS_ASSESSMENT.md | standard |
| gate-02 | gate | Evolution Approval | execution-readiness → decision | critical |
| outcome-methodology-implementation | outcome | Implement (triad mode, Steps 1-12), `change_class: significant` | gate-02 → files modified; CHANGE_MANIFEST (SEQUENCE.md) | critical |
| implementation-tactical | outcome | Implement (linear mode L1-L4), `change_class: tactical` | classify-change → IMPLEMENTATION_REPORT.md | standard |
| tail-decision-recording | outcome (tail) | Create ADR | either implementation (`depends_on_mode: any`) → ADR-*.md | standard |
| tail-documentation-sync | outcome (tail) | Update affected docs | either implementation (`depends_on_mode: any`) → DOCUMENTATION_PROPOSAL.md | standard |
| sequence-complete | terminal | End | both tails (join rule default all_success) | UNSTATED |

## Routes, gates, loops and contracts as declared
- Sequence type `strict` (DAG metadata + SEQUENCE.md) → UC-EXEC-POLICY strict for both paths.
- Router `classify-change.routes`: `tactical: [implementation-tactical]`, `significant: [outcome-research-synthesis]`. Default: prose "Default is significant. If ANY criterion is not met, route to significant path." → routing node with explicit default `significant`.
- Override (SEQUENCE.md prose): "If the user disagrees with the classification, they may override with documented justification." significant→tactical requires confirming all 5 TC; tactical→significant needs none → an input gate after the router, not modelled in DAG.
- Tactical escalation (prose, implementation-tactical): "If scope exceeds tactical during L1, STOP and escalate to significant path." → route from implementation-tactical to outcome-research-synthesis; no DAG edge.
- `gates.gate-research-options-approval` (gate-01 via `spec_ref`): 7 criteria, `approval_required: true`, `decisions: [PROCEED, REVISE, REJECT]`, `applies_to: significant`. on_failure UNSTATED; REVISE target UNSTATED (SEQUENCE.md: "Research or options need iteration").
- `gates.gate-evolution-approval` (gate-02): 6 criteria (SEQUENCE.md adds "User accepts the proposed change"), same decisions. REVISE target UNSTATED ("Evolution needs iteration"). REJECT → prose "Abandon change".
- Loops: none declared. Gate REVISE is the only re-entry (Type B, orchestrator-managed).
- Tails: `tail: true`, `parallel_with` each other, `depends_on_mode: "any"` on both implementations → join any_success; SEQUENCE.md `tail_outcomes.trigger: on_success, parallel: true`; "Tail outcomes are mandatory, not optional".
- sequence-complete: no join_rule → default all_success over both tails.
- Handoff contracts (all `from`/`to` use outcome ids, not DAG node ids):
  1. research-synthesis → options-analysis: RESEARCH_SYNTHESIS.md, RECOMMENDATION.md (exists), `research_findings` (array minItems 1, schema) → `block`, retry max_attempts 1, backoff none.
  2. options-analysis → methodology-evolution (through gate-01): OPTIONS_ANALYSIS.md, `selected_approach` {recommendation, rationale}; constraint RES-OPTIONS-COMPLETE binding → `block`, retry 1.
  3. methodology-evolution → stress-testing: EVOLUTION_PROPOSAL.md, TENSION_REPORT.md, `lens_verdicts` {consensus, lead_lens_verdict ∈ PROCEED|CONDITIONAL|BLOCK} → `block`.
  4. stress-testing → execution-readiness: STRESS_TEST_REPORT.md, `stress_test_results` {verdict ∈ PASS|CONDITIONAL|FAIL, failure_modes} → `block`.
  5. execution-readiness → methodology-implementation (through gate-02): READINESS_ASSESSMENT.md, `readiness_status` {ready, comprehension_verified}; constraints EVO-APPROVED, TRIAD-CONSENSUS, STRESS-TESTED, READY (binding) → `block`.
  6. methodology-implementation → decision-recording: `implementation_complete` {files_modified, tests_passed} → `warn`.
  7. methodology-implementation → documentation-sync: `documentation_changes` → `warn`.
- Completion orders (SEQUENCE.md): before declaring complete, `recorded_checksums.json` must exist, and if any artifact changed `.sulis/change-manifests/{primary-artifact-id}.json` must exist; "If absent: BLOCKED" → postcondition on sequence-complete.

## Scenarios
### S1 — Tactical happy path
- Inputs: change_name="fix-index-version", change_spec="correct version in index.md"
- Scripted: scope-capture → done; classify-change → tactical (TC-01..05 all true); implementation-tactical → complete; tails → complete; completion orders satisfied
- Expect visited: [scope-capture, classify-change, implementation-tactical, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: []
- Expect terminal: complete
### S2 — Significant happy path
- Inputs: change_name="add-while-node", change_spec="new node type"
- Scripted: classify-change → significant; all outcomes → complete; gate-01 → approve (PROCEED); gate-02 → approve (PROCEED); handoffs 1-7 satisfied
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-methodology-evolution, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-methodology-implementation, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S3 — Router default (unmatched criteria → significant)
- Inputs: change_spec with TC-03 not assessable
- Scripted: classify-change → no classification value / not all TC true
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis, ...as S2]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S4 — Gate 1 send back once
- Scripted: gate-01 → send_back (REVISE) with note, rerun options-analysis (best reading), then gate-01 → approve; rest as S2
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-options-analysis, gate-01, outcome-methodology-evolution, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-methodology-implementation, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: send_back, gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S5 — Gate 1 reject
- Scripted: gate-01 → reject (REJECT)
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis, outcome-options-analysis, gate-01]
- Expect gates: [gate-01: reject]
- Expect terminal: rejected
### S6 — Gate 2 send back once
- Scripted: gate-01 → approve; gate-02 → send_back, rerun outcome-methodology-evolution → stress-testing → execution-readiness (best reading); gate-02 → approve
- Expect visited: [..., outcome-execution-readiness, gate-02, outcome-methodology-evolution, outcome-stress-testing, outcome-execution-readiness, gate-02, outcome-methodology-implementation, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: send_back, gate-02: approve]
- Expect terminal: complete
### S7 — Gate 2 reject
- Scripted: gate-01 → approve; gate-02 → reject
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis, outcome-options-analysis, gate-01, outcome-methodology-evolution, outcome-stress-testing, outcome-execution-readiness, gate-02]
- Expect gates: [gate-01: approve, gate-02: reject]
- Expect terminal: rejected
### S8 — Tactical escalated at L1
- Scripted: classify-change → tactical; implementation-tactical → escalate (scope exceeds tactical); significant path as S2
- Expect visited: [scope-capture, classify-change, implementation-tactical, outcome-research-synthesis, outcome-options-analysis, gate-01, ..., outcome-methodology-implementation, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete
### S9 — User overrides significant → tactical
- Scripted: classify-change → significant; override input → tactical with justification confirming TC-01..05
- Expect visited: [scope-capture, classify-change, implementation-tactical, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [override: approve (recorded justification)]
- Expect terminal: complete
### S10 — Handoff `block`: research output missing
- Scripted: outcome-research-synthesis → complete but RECOMMENDATION.md absent; contract 1 retry (max_attempts 1) still absent
- Expect visited: [scope-capture, classify-change, outcome-research-synthesis]
- Expect gates: []
- Expect terminal: blocked ("Research synthesis must be complete before options analysis can begin")
### S11 — Handoff `warn`: implementation summary incomplete
- Scripted: significant path as S2; outcome-methodology-implementation → complete without `tests_passed`; `documentation_changes` absent
- Expect visited: [..., outcome-methodology-implementation, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect gates: [gate-01: approve, gate-02: approve]
- Expect terminal: complete (two warnings recorded)
### S12 — Tail failure blocks the all_success join
- Scripted: S1 path; tail-documentation-sync → failed; tail-decision-recording → complete
- Expect visited: [scope-capture, classify-change, implementation-tactical, {tail-decision-recording | tail-documentation-sync}]
- Expect gates: []
- Expect terminal: blocked (sequence-complete never ready)
### S13 — Completion order unmet
- Scripted: S1 path; methodology artifact changed but no CHANGE_MANIFEST file
- Expect visited: [scope-capture, classify-change, implementation-tactical, {tail-decision-recording | tail-documentation-sync}, sequence-complete]
- Expect terminal: blocked (CHANGE_MANIFEST missing)

## Ambiguities for the process owner
- Node types `scope_capture`, `router`, `terminal` and fields `routes`, `path`, `depends_on_mode`, `tail`, `parallel_with`, `outputs`, `context` are not in DAG_SCHEMA_SPECIFICATION (which allows only step/outcome/gate and `join_rule`).
- Handoff contract `from`/`to` ids (`research-synthesis`) do not match DAG node ids (`outcome-research-synthesis`); no contract for the tactical path (classify-change → implementation-tactical, implementation-tactical → tails).
- Gate REVISE targets UNSTATED for both gates; gate on_failure UNSTATED. Scenarios S4/S6 are a best reading.
- Gate decision vocabulary PROCEED/REVISE/REJECT differs from the schema's `on_failure: REVISE|REJECT` and other sequences' APPROVED/REJECTED.
- Terminal verdict names (rejected, blocked) UNSTATED; only `sequence-complete` exists.
- Tactical L1 escalation and user override exist only in prose; no DAG route or gate.
- sequence-complete has no join rule: default all_success means a failed tail blocks completion, while tails are "mandatory" — failure behaviour UNSTATED.
- Gate-02 SEQUENCE.md adds a criterion ("User accepts the proposed change") and gate-01 adds "Escalation recommendations (if any) are clear"; DAG adds "All three lenses have signed off" and "Triad verdict is PROCEED" — criteria lists differ.
- Contract 5 constraint TRIAD-CONSENSUS requires PROCEED, but `lens_verdicts` allows CONDITIONAL/BLOCK; what happens on CONDITIONAL is UNSTATED.
- Contracts 1 and 2 retry max_attempts 1 (no retry in practice); contracts 3-7 retry UNSTATED.
- Version skew: DAG v3.0.0 (updated 2026-03-05) vs SEQUENCE.md 4.x; version history lists 4.2.0 above 4.0.0 while the header says 4.0.0. No SEQUENCE.yaml.
- Scope-capture checksum recording and CHANGE_MANIFEST emission are prose-only obligations with no node.
