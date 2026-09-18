# outcome-review — content

Source: apps/api/sulis/services/content/workflows/outcome_review_workflow.py (+ processes.py `OUTCOME_REVIEW`)
Purpose: An independent agent judges an agent's answer against the confirmed Instruction's acceptance criteria, and the person accepts it or sends the work back.
Use cases: UC-IN-TYPED, UC-OUT-TYPED, UC-OUT-MODE, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-HANDOFF, UC-GATE-AUDIT, UC-RETRY, UC-RESUME, UC-STOP-NAMED

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (input seeding) | — | `inputs_for`: the confirmed Instruction, the answer verbatim, proposed changes or a "no change" sentence. No `max-cycles`. | brief → `instruction`, `answer`, `changes` |
| main | judge | agent (`probabilistic`) | Per criterion MET / NOT_MET / UNCLEAR with evidence; `overall`; summary. Checked against the `verdict` schema. | `instruction`, `answer`, `changes` → `verdict` |
| main | accept | human (APPROVAL, default kind) | Person accepts or sends back with a note. | `verdict` → `acceptance` |

## Routes as declared
- `initial_steps: [judge]`; `judge -> accept`; `terminal_steps: [accept]`. No cycle-back.
- PERMIT → `workflow_complete` (verdict pass); host marks the Instruction accepted and publishes proposed changes as pull requests (`instruction_flow.py:643-671`).
- DENY → no declared way back → recorded `escalated` in the run; `revise_redoes = False` so the brief closes `sent_back`; host starts a new instruction-generation brief from the note (`gate_engine.py:249-253`, `instruction_flow.py:672-700`).
- INDETERMINATE → `escalated`; no host follow-on declared.
- ABANDON (brief vocabulary) → run stopped; host marks the Instruction abandoned.
- Output mode `stored` only. `overall` (MET/NOT_MET/UNCLEAR) does not route.

## Scenarios
### S1 — Work accepted
- Inputs: `instruction` = confirmed Instruction (3 criteria); `answer` = agent's reply; `changes` = one branch
- Scripted: judge → overall MET; accept → PERMIT
- Expect visited: [judge, accept]
- Expect gates: [accept: PERMIT]
- Expect terminal: workflow_complete (verdict pass; host publishes the pull request)

### S2 — Sent back: new Instruction raised
- Inputs: as S1
- Scripted: judge → overall NOT_MET; accept → DENY "the PDF export still has no spinner"
- Expect visited: [judge, accept]
- Expect gates: [accept: DENY]
- Expect terminal: escalated:accept (brief `sent_back`; host handoff → `instruction-generation` S7)

### S3 — Accepted despite an unclear verdict
- Inputs: as S1, `changes` default "None"
- Scripted: judge → overall UNCLEAR; accept → PERMIT
- Expect visited: [judge, accept]
- Expect gates: [accept: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S4 — Person cannot decide
- Inputs: as S1
- Scripted: accept → INDETERMINATE
- Expect visited: [judge, accept]
- Expect gates: [accept: INDETERMINATE]
- Expect terminal: escalated:accept

### S5 — Abandoned
- Inputs: as S1
- Scripted: accept → ABANDON
- Expect visited: [judge, accept]
- Expect gates: [accept: ABANDON]
- Expect terminal: cancelled (host)

### S6 — Verdict fails its schema, then passes
- Inputs: as S1
- Scripted: judge report#1 → `overall` missing → refused; report#2 → valid; accept → PERMIT
- Expect visited: [judge, accept]
- Expect gates: [accept: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

## Ambiguities for the process owner
- The send-back handoff (end this run, start instruction-generation with the note) is declared only in Python (`processes.py` `revise_redoes=False`, `instruction_flow.py`), not in the workflow; the run itself records a plain escalation, indistinguishable from a real failure.
- ABANDON and REVISE both map to DENY at the accept decision (`instruction_flow.py:659`) but lead to different host outcomes; the verdict alone does not say which.
- INDETERMINATE has no follow-on: the Instruction stays awaiting acceptance.
- The judge's `overall` never routes; a NOT_MET verdict accepted by the person completes normally. Whether that is intended is unstated.
- A second send-back on the revised work starts yet another instruction; no budget across that chain is declared.
