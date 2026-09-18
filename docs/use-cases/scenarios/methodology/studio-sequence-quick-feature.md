# quick-feature — methodology studio sequence

Source: methodology/studios/product-development/sequences/quick-feature/SEQUENCE.yaml, methodology/delivery/product/SEQUENCES.md §quick-feature and §YAML Definition (schema meaning: methodology/studios/STUDIO_SCHEMA.md)
Purpose: Ship a small change with minimal ceremony: goal, implementation, quality, one release approval.
Use cases: UC-SEQUENCE, UC-CALL, UC-EXEC-POLICY, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-CRITERIA, UC-GATE-AUDIT, UC-STOP-NAMED

## Steps
| Step / outcome | Type | Does | Depends on / reads → writes | Criticality |
|---|---|---|---|---|
| 1 goal | outcome | Goal and success criteria | — / feature name → goal artifact | UNSTATED |
| 2 solution-implementation | outcome | Implements the change | goal / goal artifact → code, tests | UNSTATED |
| 3 production-quality | outcome | Verification incl. Production Guardian | solution-implementation / code → VERIFICATION_REPORT.md | UNSTATED |
| Release Approval | gate (user_approval) | Person approves release | production-quality / tests, goal, guardian verdict → decision | UNSTATED |

## Routes, gates, loops and contracts as declared
- Type `strict`: "all outcomes execute in order." No optional steps.
- Linear order: goal → solution-implementation → production-quality → Release Approval.
- Release Approval (`gate_after` step 3, `user_approval`), criteria (prose): "Review tests, verify goal met, Production Guardian APPROVED". Decisions: runtime APPROVED|REJECTED; send-back and on_failure UNSTATED.
- Tail outcomes: none declared (SEQUENCE.yaml and SEQUENCES.md).
- Handoffs: none declared. No loops, spirals or triads at sequence level.

## Scenarios
### S1 — Approved
- Inputs: feature_name="fix-composer-growth"
- Scripted: goal → complete; solution-implementation → complete; production-quality → complete (Guardian APPROVED); Release Approval → approve
- Expect visited: [goal, solution-implementation, production-quality, Release Approval]
- Expect gates: [Release Approval: approve]
- Expect terminal: complete

### S2 — Rejected
- Inputs: feature_name="fix-composer-growth"
- Scripted: goal, solution-implementation, production-quality → complete (tests failing); Release Approval → reject
- Expect visited: [goal, solution-implementation, production-quality, Release Approval]
- Expect gates: [Release Approval: reject]
- Expect terminal: rejected (name UNSTATED)

### S3 — Strict order: skipping implementation refused
- Inputs: feature_name="fix-composer-growth", skip=[solution-implementation] without explicit approval
- Scripted: goal → complete; skip request → refused
- Expect visited: [goal, solution-implementation, …] (skip not honoured)
- Expect gates: []
- Expect terminal: n/a (run continues in order; refusal recorded)

## Ambiguities for the process owner
- No send-back from Release Approval; what happens after a rejection (abandon vs rework) is unstated.
- "Deviation requires explicit approval" for strict type has no declared mechanism for asking or recording that approval.
- No tail outcomes, unlike every sibling sequence; decisions from quick changes are not recorded.
- Terminal verdict names and criticality not declared.
