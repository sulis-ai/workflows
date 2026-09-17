# instruction-generation — content

Source: apps/api/sulis/services/content/workflows/instruction_generation_workflow.py (+ processes.py `INSTRUCTION_GENERATION`)
Purpose: Turn a person's ask into a schema-checked Instruction (reading, filled-in gaps, acceptance criteria, route) that the person confirms or sends back.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-OUT-TYPED, UC-OUT-MODE, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-AUDIT, UC-GATE-HANDOFF, UC-LOOP-BUDGET, UC-RETRY, UC-RESUME, UC-STOP-NAMED

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (input seeding) | — | `inputs_for`: person's words verbatim, prior Instruction or a "first reading" sentence, `max-cycles = 3`. | brief → `conversation_excerpt`, `prior_instruction`, `max-cycles` |
| main | interpret | agent (`probabilistic`) | Writes the Instruction JSON: ask as given, summary, reading, filled-in gaps with basis, criteria, route (execute/decompose/inquire), confidence. Output checked against the `instruction` schema before recording. | `conversation_excerpt`, `prior_instruction`, `confirm` → `instruction` |
| main | confirm | human (APPROVAL, default kind) | Person confirms, or denies with a note. | `instruction` → `confirmation` |

## Routes as declared
- `initial_steps: [interpret]`; `interpret -> confirm`; `terminal_steps: [confirm]`.
- `confirm -> interpret [META-SPIRAL cycle-back: decision == DENY]`; budget `max-cycles = 3` passes of `interpret` (two redos); counter = completed `interpret` records.
- DENY with no redo left, or INDETERMINATE → `escalated`.
- PERMIT → `workflow_complete` (verdict pass). Output mode `stored` only.
- Schema refusal of `interpret`'s report: refused before anything is recorded; the agent corrects and reports again (no attempt consumed; `service.py:_validate`). Budget for refusals: UNSTATED.
- After completion (host, not the definition): route `execute` → handed to agents; `decompose` → host starts `instruction-decomposition` (`instruction_flow.py:268-272`, `instruction_routes.py:32-60`); `inquire` → delivered as a question.

## Scenarios
### S1 — Confirmed first time, work handed over
- Inputs: `conversation_excerpt` = "make the export button show a spinner"; `prior_instruction` default
- Scripted: interpret → valid Instruction, route execute, confidence grounded; confirm → PERMIT
- Expect visited: [interpret, confirm]
- Expect gates: [confirm: PERMIT]
- Expect terminal: workflow_complete (verdict pass; host hands over, route execute)

### S2 — Confirmed, too big: split requested
- Inputs: `conversation_excerpt` = "rebuild the reporting area"
- Scripted: interpret → route decompose; confirm → PERMIT
- Expect visited: [interpret, confirm]
- Expect gates: [confirm: PERMIT]
- Expect terminal: workflow_complete (verdict pass; host starts instruction-decomposition)

### S3 — Sent back once with a note
- Inputs: as S1
- Scripted: confirm#1 → DENY "only on the CSV export"; interpret#2 (note in prompt) → revised Instruction; confirm#2 → PERMIT
- Expect visited: [interpret, confirm, interpret#2, confirm#2]
- Expect gates: [DENY → cycle back, PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S4 — Sent back with no redo left
- Inputs: as S1
- Scripted: confirm#1, #2, #3 → DENY
- Expect visited: [interpret, confirm, interpret#2, confirm#2, interpret#3, confirm#3]
- Expect gates: [DENY, DENY, DENY → no redo left]
- Expect terminal: escalated:confirm

### S5 — Not the person's call
- Inputs: as S1
- Scripted: confirm → INDETERMINATE
- Expect visited: [interpret, confirm]
- Expect gates: [confirm: INDETERMINATE]
- Expect terminal: escalated:confirm

### S6 — First report fails the schema
- Inputs: as S1
- Scripted: interpret report#1 → missing `acceptance_criteria` → refused with violations; report#2 → valid; confirm → PERMIT
- Expect visited: [interpret (one recorded attempt), confirm]
- Expect gates: [confirm: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S7 — Revision raised by an outcome review
- Inputs: `conversation_excerpt` = "The person asking: also cover the PDF export"; `prior_instruction` = prior Instruction JSON
- Scripted: interpret → revised Instruction; confirm → PERMIT
- Expect visited: [interpret, confirm]
- Expect gates: [confirm: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

## Ambiguities for the process owner
- `confirm` is a required input of `interpret` but is absent on the first pass (same as content-generation).
- The route (`execute`/`decompose`/`inquire`) is decided inside the output and acted on by the host after completion; the definition declares no branch for it, so the process handoff is invisible in the workflow (UC-GATE-HANDOFF).
- `confidence: insufficient` is written into the Instruction but routes nowhere in the definition; the person still confirms it.
- No budget for schema refusals of a report; an agent can be refused indefinitely.
- Budget (`max-cycles`) lives in `processes.py`, not in the workflow definition.
- A passing report "cannot be replaced" (instructions prose); the engine rule that makes this so is not declared in the workflow.
