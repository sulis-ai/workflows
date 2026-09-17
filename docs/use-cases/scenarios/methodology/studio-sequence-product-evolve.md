# product-evolve — methodology studio sequence

Source: methodology/studios/product-development/sequences/product-evolve/SEQUENCE.yaml, methodology/delivery/product/SEQUENCES.md §product-evolve and §YAML Definition, methodology/outcomes/utility/change-diagnosis/OUTCOME.md (routing tiers) (schema meaning: methodology/studios/STUDIO_SCHEMA.md)
Purpose: Diagnose a change to existing product artifacts, run only the outcome(s) the diagnosis routes to, then verify quality, with a gate after each.
Use cases: UC-SEQUENCE, UC-CALL, UC-DECIDE, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-PATHS, UC-STOP-NAMED, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-GATE-HANDOFF, UC-EXEC-POLICY, UC-HANDOFF, UC-OUT-MULTI

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 change-diagnosis | outcome (decide) | Classifies the change (Tier 1 Trivial, Tier 2 Trivial, Patch, Minor, Major) and recommends outcome(s) | — / change description, FUNCTION.md, STANDARDS.md, VOCABULARY.md → CHANGE_DIAGNOSIS.md (scope, routed outcome slug(s), confidence) | UNSTATED |
| COND-01 practitioner confirmation | gate (input/approval, prose) | Person confirms a single-outcome routing | change-diagnosis / routed slug → confirmation | UNSTATED |
| 2 {routed outcome(s)} | routing → outcome(s) (runtime-resolved) | Runs the routed outcome(s) | change-diagnosis / CHANGE_DIAGNOSIS.md → outcome artifacts | UNSTATED |
| {Outcome} Approved | gate (user_approval, runtime-named) | Approve the routed work | step 2 / outcome artifacts → decision | UNSTATED |
| 3 production-quality | outcome | Verification scoped to affected categories | gate / → VERIFICATION_REPORT.md | UNSTATED |
| Quality Verified | gate (user_approval + automated) | Approve quality | production-quality / report → decision | UNSTATED |
| decision-recording | outcome (tail) | ADR | Quality Verified / → ADR | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `guided`. SEQUENCE.yaml steps: 1 change-diagnosis, 3 production-quality; step 2 is a comment: "runtime-routed outcome(s) — resolved from change-diagnosis output … Not modelled statically; SequenceExecutionEngine inserts dynamically." Gate after step 2 name "{Outcome} Approved".
- Routing (SEQUENCES.md prose, field = scope classification in CHANGE_DIAGNOSIS.md):
  - Tier 1 / Tier 2 Trivial → "change-diagnosis fast-exits; no sequence invoked" (Tier 1: no artifact; "Direct fix").
  - Patch → "specific outcome for targeted fix" (change-diagnosis: "Function's implementation outcome").
  - Minor → "affected outcome(s) with standard verification" (design + implementation outcomes).
  - Major → "multiple outcomes; may recommend product-delivery instead" ("Function's full create sequence").
  - Default: UNSTATED.
- COND-01: "When change-diagnosis routes to a single outcome, the practitioner confirms the routing before proceeding." Rejection path UNSTATED.
- Gates: "{Outcome} Approved" criteria = "Outcome-specific criteria from product-delivery gates"; "Quality Verified" = "Affected verification categories PASS", type "user_approval + automated". Runtime decisions APPROVED|REJECTED; send-back UNSTATED.
- Tails: `[decision-recording]`, `trigger: on_success` (no `parallel`).
- Handoffs: none declared beyond gate criteria. No loops, spirals or triads at sequence level (change-diagnosis has its own standard-tier spiral, max 3).

## Scenarios
### S1 — Patch routed to one outcome, confirmed, approved
- Inputs: change_description="IVS amendment for retry semantics"
- Scripted: change-diagnosis → complete (scope=Patch, routed=[solution-implementation]); COND-01 → approve; solution-implementation → complete; {Outcome} Approved → approve; production-quality → complete; Quality Verified → approve; decision-recording → complete
- Expect visited: [change-diagnosis, COND-01, solution-implementation, "Solution-implementation Approved", production-quality, Quality Verified, decision-recording]
- Expect gates: [COND-01: approve, Solution-implementation Approved: approve, Quality Verified: approve]
- Expect terminal: complete

### S2 — Minor routed to several outcomes (no COND-01)
- Inputs: change_description="add a new interface to the design"
- Scripted: change-diagnosis → complete (scope=Minor, routed=[solution-design, solution-implementation]); solution-design → complete; solution-implementation → complete; {Outcome} Approved → approve; production-quality → complete; Quality Verified → approve; decision-recording → complete
- Expect visited: [change-diagnosis, solution-design, solution-implementation, {Outcome} Approved, production-quality, Quality Verified, decision-recording]
- Expect gates: [{Outcome} Approved: approve, Quality Verified: approve]
- Expect terminal: complete

### S3 — Tier 1 Trivial fast-exit
- Inputs: change_description="fix a typo in USER_GUIDE.md"
- Scripted: change-diagnosis → complete (scope=Tier 1 Trivial, no artifact)
- Expect visited: [change-diagnosis]
- Expect gates: []
- Expect terminal: fast-exit (name UNSTATED; "no sequence invoked"; tail not run)

### S4 — Tier 2 Trivial fast-exit
- Inputs: change_description="reword a heading with no semantic change"
- Scripted: change-diagnosis → complete (scope=Tier 2 Trivial, CHANGE_DIAGNOSIS.md written)
- Expect visited: [change-diagnosis]
- Expect gates: []
- Expect terminal: fast-exit

### S5 — Major recommends product-delivery
- Inputs: change_description="new sub-function across billing and identity"
- Scripted: change-diagnosis → complete (scope=Major, recommendation=product-delivery)
- Expect visited: [change-diagnosis]
- Expect gates: []
- Expect terminal: handed off to product-delivery (best reading of "may recommend product-delivery instead"; alternative: routed to multiple outcomes as S2)

### S6 — Routed outcome rejected
- Inputs: change_description="IVS amendment for retry semantics"
- Scripted: change-diagnosis → Patch; COND-01 → approve; routed outcome → complete; {Outcome} Approved → reject
- Expect visited: [change-diagnosis, COND-01, solution-implementation, {Outcome} Approved]
- Expect gates: [COND-01: approve, {Outcome} Approved: reject]
- Expect terminal: rejected (name UNSTATED)

### S7 — Quality rejected
- Inputs: as S1
- Scripted: as S1 to production-quality (category BLOCKED); Quality Verified → reject
- Expect visited: [change-diagnosis, COND-01, solution-implementation, {Outcome} Approved, production-quality, Quality Verified]
- Expect gates: [COND-01: approve, {Outcome} Approved: approve, Quality Verified: reject]
- Expect terminal: rejected

## Ambiguities for the process owner
- Step 2 and its gate are not in the machine definition at all; the routing field, allowed outcome slugs and default route are unstated.
- The "{Outcome} Approved" gate name and criteria are runtime-resolved; with several routed outcomes it is unclear whether there is one gate or one per outcome, and whether routed outcomes run in order or in parallel.
- COND-01 confirmation has no declared decline path (re-diagnose? abort?).
- Major: "may recommend product-delivery instead" does not say whether this run ends, hands off, or continues.
- Fast-exit verdict name and whether the tail runs on fast-exit are unstated.
- "user_approval + automated" for Quality Verified: order and effect of the automated part unstated.
- No send-back routes, budgets, handoff contracts, criticality or terminal names.
- product-evolve tails are not marked parallel (only one tail), unlike the sibling sequences.
