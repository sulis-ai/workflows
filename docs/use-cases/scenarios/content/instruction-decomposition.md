# instruction-decomposition — content

Source: apps/api/sulis/services/content/workflows/instruction_decomposition_workflow.py (+ processes.py `INSTRUCTION_DECOMPOSITION`)
Purpose: Split a confirmed Instruction too large for one piece into ordered, non-overlapping child asks that together cover every acceptance criterion, confirmed by the person.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-TYPED, UC-OUT-MODE, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-AUDIT, UC-GATE-HANDOFF, UC-LOOP-BUDGET, UC-FOREACH, UC-RETRY, UC-STOP-NAMED

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (input seeding) | — | `inputs_for`: the confirmed Instruction JSON, `max-cycles = 3`. Started by the host, auto-submitted. | brief → `instruction`, `max-cycles` |
| main | split | agent (`probabilistic`) | Writes `children` (ordered asks, each naming the criteria it `covers`) and `why`. Checked against the `decomposition` schema. | `instruction`, `confirm-split` → `decomposition` |
| main | confirm-split | human (APPROVAL, default kind) | Person confirms the split or sends it back with a note. | `decomposition` → `split_confirmation` |

## Routes as declared
- `initial_steps: [split]`; `split -> confirm-split`; `terminal_steps: [confirm-split]`.
- `confirm-split -> split [META-SPIRAL cycle-back: decision == DENY]`; budget `max-cycles = 3` passes of `split`.
- DENY with no redo left, or INDETERMINATE → `escalated`.
- PERMIT → `workflow_complete` (verdict pass). Output mode `stored`.
- After completion (host): child 1 is raised as a new instruction-generation brief; each next child is raised when the previous piece closes (`instruction_routes.py:63-110`).

## Scenarios
### S1 — Split confirmed, first piece asked for
- Inputs: `instruction` = confirmed Instruction with 4 criteria, route decompose
- Scripted: split → 3 children covering all 4 criteria; confirm-split → PERMIT
- Expect visited: [split, confirm-split]
- Expect gates: [confirm-split: PERMIT]
- Expect terminal: workflow_complete (verdict pass; host handoff → instruction-generation for child 1)

### S2 — Split sent back once
- Inputs: as S1
- Scripted: confirm-split#1 → DENY "do the data model first"; split#2 → reordered; confirm-split#2 → PERMIT
- Expect visited: [split, confirm-split, split#2, confirm-split#2]
- Expect gates: [DENY → cycle back, PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S3 — Sent back with no redo left
- Inputs: as S1
- Scripted: confirm-split#1, #2, #3 → DENY
- Expect visited: [split, confirm-split, split#2, confirm-split#2, split#3, confirm-split#3]
- Expect gates: [DENY, DENY, DENY → no redo left]
- Expect terminal: escalated:confirm-split

### S4 — Person cannot decide
- Inputs: as S1
- Scripted: confirm-split → INDETERMINATE
- Expect visited: [split, confirm-split]
- Expect gates: [confirm-split: INDETERMINATE]
- Expect terminal: escalated:confirm-split

### S5 — Split fails its schema
- Inputs: as S1
- Scripted: split report#1 → a child without `covers` → refused; report#2 → valid; confirm-split → PERMIT
- Expect visited: [split, confirm-split]
- Expect gates: [confirm-split: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

## Ambiguities for the process owner
- The coverage rule (every criterion covered exactly once) is prose in the agent instructions; nothing declared checks it before the person sees the split, beyond the schema's shape.
- The for-each over children (sequential, one confirmed Instruction per piece) is host Python, not declared by any process.
- `confirm-split` is a required input of `split` but absent on the first pass.
- The budget (`max-cycles`) lives in `processes.py`, not in the workflow.
- A split with a single child, or a child that itself needs splitting, has no declared handling; recursion depth across nested decompositions is unbounded.
