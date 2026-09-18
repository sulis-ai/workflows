# research-synthesis — methodology outcome

Source: methodology/outcomes/utility/research-synthesis/GRAPH.yaml (v1.3.4), methodology/outcomes/utility/research-synthesis/OUTCOME.md, methodology/outcomes/utility/research-synthesis/lenses/ (evidence-gatherer.md, source-critic.md, coherence-analyst.md)
Purpose: Gather external evidence, rate its credibility, synthesise it with SCQA framing under a three-lens review loop, extract reusable knowledge, and verify the result.
Use cases: UC-SEED-ARTIFACTS, UC-STATE-CHANNELS, UC-OUT-MULTI, UC-MECHANISM, UC-CRITICALITY, UC-PRECONDITION, UC-PARALLEL, UC-JOIN, UC-LENS-TRIAD, UC-VERDICT-ROUTE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-LOOP-BUDGET, UC-LOOP-MANY, UC-SPIRAL, UC-STOP-NAMED, UC-STOP-HONEST

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| define-research-scope | step (content) | Extracts topic, scope, success criteria; detects profile competitive/default | [] / BRIEF.md → profile, proposal_ready; PROPOSAL.md | critical |
| evidence-gathering | step (content) | Inventories ≥3 external sources (Evidence Gatherer lens) | define-research-scope / profile, proposal_ready, PROPOSAL.md → evidence_ready, source_inventory; lenses/evidence-gatherer/ANALYSIS.md | standard |
| source-credibility-assessment | step (content) | Tier 1–4 rating, bias notes (Source Critic lens) | evidence-gathering / evidence_ready, source_inventory, … → credibility_ready, credibility_assessment; lenses/source-critic/ANALYSIS.md | standard |
| coherence-analysis | step (content) | Convergence/divergence map weighted by tier (Coherence Analyst lens) | source-credibility-assessment / credibility_* , source_inventory, … → coherence_ready, coherence_map; lenses/coherence-analyst/ANALYSIS.md | standard |
| synthesis-and-documentation | step (content) | Drafts SCQA synthesis; template by profile; on revision pass addresses prior REVISE notes | coherence-analysis (and back-edge from sign-off-router) / profile, *_ready, coherence_map, 3 ANALYSIS.md → synthesis_ready; synthesis/RESEARCH_SYNTHESIS.md | critical |
| evidence-gatherer-sign-off | step (content) | Independent PROCEED/REVISE on coverage | synthesis-and-documentation / synthesis_ready, synthesis, own ANALYSIS → lenses/evidence-gatherer/SIGN_OFF.md | standard |
| source-critic-sign-off | step (content) | Independent PROCEED/REVISE on credibility | synthesis-and-documentation / … → lenses/source-critic/SIGN_OFF.md | standard |
| coherence-analyst-sign-off | step (content) | Independent PROCEED/REVISE on coherence + SCQA (lead lens) | synthesis-and-documentation / … → lenses/coherence-analyst/SIGN_OFF.md | standard |
| composite-verdict | step (content) | proceed only if all 3 PROCEED; increments iteration_count; at 3 forces proceed and logs override | 3 sign-offs / 3 SIGN_OFF.md → sign_off_verdict, iteration_count; COMPOSITE_VERDICT.md | standard |
| sign-off-router | routing | Routes on sign_off_verdict | composite-verdict / sign_off_verdict | UNSTATED |
| knowledge-extraction | step (content) | Writes patterns/findings/proof-points/sources to product/knowledge/, index, standard-candidate flags; or NO_KNOWLEDGE_EXTRACTED.md | sign-off-router / sign_off_verdict, synthesis, SIGN_OFF.md ×3 → knowledge_ready; product/knowledge/INDEX.md | critical |
| activity-verify | step (content) | STANDARD_TIER_DEFAULT verification spiral → VERIFICATION_REPORT.md | knowledge-extraction / (reads UNSTATED) → VERIFICATION_REPORT.md (verification_complete not declared as written) | critical |

## Routes, gates, loops and contracts as declared
- **Seeded input:** `input_artifacts: [{path: "BRIEF.md"}]` → seed-artifact from the brief (shape differs from schema `source_outcome`/`files`).
- **Joins:** composite-verdict depends_on the three sign-offs; `join_rule` UNSTATED → schema default `all_success`. The three sign-offs share one predecessor → static parallel fan-out (no `fan_out` node).
- **Routing:** `sign-off-router` field `sign_off_verdict`; routes `proceed → knowledge-extraction`, `revise → synthesis-and-documentation`; `default: synthesis-and-documentation`; `max_iterations: 3`; `exit_condition` UNSTATED.
- **Loop budget in a step:** composite-verdict prose: "If iteration_count has reached 3, override any REVISE verdicts, force sign_off_verdict to 'proceed', and log the iteration-limit override in all three SIGN_OFF.md files." → loop exhaustion routes forward (proceed), not to a stop.
- **Verdict vocabulary:** sign-offs PROCEED | REVISE; composite proceed | revise.
- **Lens triad:** Evidence Gatherer, Source Critic, Coherence Analyst (lead). Three independent sign-offs + composite = lens-triad.
- **Gates:** no `gate` nodes, no `gates:` block. OUTCOME.md "Gate Criteria" (15 criteria) are completion criteria; "If criteria not met: Return to relevant step and iterate." (prose only, no target).
- **Preconditions (OUTCOME.md step specs):** each step `on_failure: blocked` → BLOCKED.md; step 1 needs a topic; step 2 POST ≥3 sources; step 7 PRE-02 "all SIGN_OFF.md files exist with PROCEED verdict".
- **Honest stop:** step 7 `termination_paths.reject: valid: true` when no extractable knowledge → NO_KNOWLEDGE_EXTRACTED.md; graph prose continues to knowledge_ready.
- **Verification spiral:** tier standard, template STANDARD_TIER_DEFAULT; node dimensions ACCA (each ≥4), Evidence Grounding ≥4, Structural Coherence ≥4, Honest Uncertainty ≥3; OUTCOME.md custom dimensions Source Credibility Assessment ≥4, Synthesis Coherence ≥4, Balanced Investigation ≥4 (scorer generating_agent); no independence check; max iterations 3; terminates on thresholds met, max iterations, or irreducible blocker (primary sources inaccessible; contradictory Tier 1 sources; evidence beyond search window) → escalate to user. Completion requires `Verdict: PASS` on disk.
- **Escalation (prose):** "When research reveals issues larger than the original question, the outcome escalates" — expressed inside RESEARCH_SYNTHESIS.md content, no route.
- **Handoff contracts:** none (outcome-level). Optional steps: none. Tail outcomes: none. Pulse sub-outcome: declared in prose, not in graph.

## Scenarios
### S1 — Happy path, all lenses proceed first pass
- Inputs: BRIEF.md = "What pricing models do developer-tool SaaS use?", profile detected `default`
- Scripted: every step → success (5 sources); all three sign-offs → PROCEED; composite → proceed (iteration_count 1); knowledge-extraction → 2 patterns; spiral → pass on pass 1
- Expect visited: [define-research-scope, evidence-gathering, source-credibility-assessment, coherence-analysis, synthesis-and-documentation, {evidence-gatherer-sign-off | source-critic-sign-off | coherence-analyst-sign-off}, composite-verdict, sign-off-router, knowledge-extraction, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S2 — One revise loop (competitive profile)
- Inputs: BRIEF.md = "Map the competitive landscape for agent runtimes", profile `competitive`
- Scripted: pass 1 source-critic-sign-off → REVISE, others PROCEED; composite → revise (iteration_count 1); router → synthesis-and-documentation; pass 2 all PROCEED; composite → proceed (2); spiral → pass
- Expect visited: [define-research-scope, evidence-gathering, source-credibility-assessment, coherence-analysis, synthesis-and-documentation, {evidence-gatherer-sign-off | source-critic-sign-off | coherence-analyst-sign-off}, composite-verdict, sign-off-router, synthesis-and-documentation, {evidence-gatherer-sign-off | source-critic-sign-off | coherence-analyst-sign-off}, composite-verdict, sign-off-router, knowledge-extraction, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S3 — Revise loop exhausted, forced proceed
- Inputs: BRIEF.md = default research topic
- Scripted: passes 1, 2, 3 coherence-analyst-sign-off → REVISE; composite passes 1–2 → revise; composite pass 3 → forced proceed with override logged in all SIGN_OFF.md; spiral → pass
- Expect visited: [define-research-scope, evidence-gathering, source-credibility-assessment, coherence-analysis, (synthesis-and-documentation, {3 sign-offs}, composite-verdict, sign-off-router) ×3, knowledge-extraction, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS), with iteration-limit override recorded in COMPOSITE_VERDICT.md

### S4 — Unmatched verdict takes declared default
- Inputs: default topic
- Scripted: composite-verdict writes sign_off_verdict = "" (not proceed/revise); pass 2 composite → proceed; spiral → pass
- Expect visited: [… composite-verdict, sign-off-router, synthesis-and-documentation, {3 sign-offs}, composite-verdict, sign-off-router, knowledge-extraction, activity-verify]
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S5 — No extractable knowledge (honest stop of the step, run continues)
- Inputs: narrow factual topic
- Scripted: all PROCEED; knowledge-extraction → NO_KNOWLEDGE_EXTRACTED.md, knowledge_ready = true; spiral → pass
- Expect visited: as S1
- Expect gates: []
- Expect terminal: complete (Verdict: PASS), knowledge output = synthesis/NO_KNOWLEDGE_EXTRACTED.md

### S6 — Too few sources blocks evidence gathering
- Inputs: obscure topic
- Scripted: evidence-gathering → only 2 sources, evidence_ready not set (step POST-02 unmet → blocked)
- Expect visited: [define-research-scope, evidence-gathering]
- Expect gates: []
- Expect terminal: blocked (BLOCKED.md)

### S7 — Spiral fails once, fixes, passes
- Inputs: default topic
- Scripted: all PROCEED; spiral pass 1 → fail (Balanced Investigation 3/5); pass 2 → pass
- Expect visited: as S1 (activity-verify runs 2 internal passes)
- Expect gates: []
- Expect terminal: complete (Verdict: PASS)

### S8 — Spiral exhausted
- Inputs: default topic
- Scripted: spiral passes 1, 2, 3 → fail
- Expect visited: as S1
- Expect gates: []
- Expect terminal: blocked (Verdict not PASS; escalated to user)

### S9 — Spiral irreducible blocker
- Inputs: topic with two contradictory Tier 1 sources
- Scripted: spiral pass 1 → irreducible blocker "contradictory Tier 1 sources"
- Expect visited: as S1
- Expect gates: []
- Expect terminal: escalated (user decision on source priority required)

## Ambiguities for the process owner
- `sign-off-router` has a back-edge but no `exit_condition` (GV-NEW-03 requires one); GV-01 also says routing graphs must stay acyclic, contradicting the Type A loop pattern this graph uses.
- Two budgets for one loop: router `max_iterations: 3` and composite-verdict's forced proceed at iteration_count 3. Unstated what the router does when its own counter is exhausted and which counter wins.
- Forced proceed contradicts step 7 PRE-02 ("all SIGN_OFF.md files exist with PROCEED verdict", on_failure blocked) — after an override the files still say REVISE.
- `join_rule` for composite-verdict is unstated; if one sign-off step fails, all_success default blocks — intended?
- `input_artifacts` uses `path:` rather than the schema's `source_outcome` + `files`.
- `reads` list file paths (BRIEF.md, PROPOSAL.md, …) that are not declared state channels (GV-NEW-01).
- State defaults `""` for bool/int/list/dict channels (e.g. iteration_count default `""`); iteration_count starting value unstated.
- `verification_complete` is declared but no node writes it; activity-verify declares no reads/writes and no `context.input`.
- Spiral dimensions differ: activity-verify lists only template defaults; OUTCOME.md adds three custom dimensions.
- Criticality disagrees: OUTCOME.md step specs say Step 1 and Step 5 are "Standard Tier"; GRAPH.yaml marks them critical.
- OUTCOME.md says Step 1 runs "All Lenses — parallel initialization"; the graph has one node.
- Escalation ("outcome escalates rather than answering a narrow question") has no structural route or terminal; only content in the synthesis.
- "Gate Criteria … If criteria not met: Return to relevant step and iterate" has no gate node and no target step.
- Knowledge index target `product/knowledge/INDEX.md` vs OUTCOME.md `product/knowledge/index.md`.
- Pulse sub-outcome ("per-execution" frequency) is not in the graph; unstated whether the engine runs it.
