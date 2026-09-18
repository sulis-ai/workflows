# content-generation — content

Source: apps/api/sulis/services/content/workflows/content_generation_workflow.py (+ processes.py `CONTENT_GENERATION`)
Purpose: An agent writes one file from a brief, and a person approves it, sends it back for a revision, or abandons the brief.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-MECHANISM, UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-AUDIT, UC-LOOP-BUDGET, UC-OUT-MODE, UC-RETRY, UC-RESUME, UC-STOP-NAMED

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (input seeding) | — | `inputs_for`: brief text, target path, standards, success criteria, `max-cycles = 3`. | brief → `brief_text`, `target_path`, `standards`, `success_criteria`, `max-cycles` |
| main | generate | agent (`probabilistic`) | Writes the file in its working copy; reports the full final text. | `brief_text`, `target_path`, `standards`, `success_criteria`, `review` → `draft` |
| main | review | human (APPROVAL, kind unstated → default) | Person approves, sends back with a note, or abandons. | `draft` → `approval` (recorded as `{decision, decided_by, note}`) |

## Routes as declared
- `initial_steps: [generate]`; `generate -> review`; `terminal_steps: [review]`.
- `review -> generate [META-SPIRAL cycle-back: decision == DENY]` → condition on the gate's recorded `decision`; loop budget `max-cycles = 3` passes of `generate`, first included (two redos). Counter = completed `generate` records (durable). Declared in `processes.py:39-42`, counting rule in `meta_spiral.py:62-72,187-205`.
- After a redo, `review` is owed again before anything else (`meta_spiral.py:190-196`).
- DENY with no redo left → recorded `escalated` → run answers `escalated` (`service.py:273-286`, `resolve_next.py:646-654`).
- INDETERMINATE → guard not satisfied → `escalated` (`service.py:273-286`).
- PERMIT at the terminal step → `workflow_complete`, run verdict `pass` (no `[terminal:…]` transitions; `resolve_next.py:295`).
- ABANDON (brief vocabulary only) → run stopped, brief `cancelled` (`gate_engine.py:229-233`). Not declared in the workflow.
- Output mode: `(repository, stored)`, default `repository` (written to a branch and proposed as a pull request).
- Failed `generate` reports: retried up to `max-attempts` (default 3) then `escalated` — declared only in engine (`record_step_result.py:41`).

## Scenarios
### S1 — Approved first time, proposed as a pull request
- Inputs: `brief_text` = "Write a CONTRIBUTING guide", `target_path` = `CONTRIBUTING.md`, standards none, output mode default
- Scripted: generate → full file text; review → PERMIT by user:ana
- Expect visited: [generate, review]
- Expect gates: [review: PERMIT]
- Expect terminal: workflow_complete (verdict pass; output `draft` → repository)

### S2 — One revision, then approved
- Inputs: as S1
- Scripted: generate#1 → text; review#1 → DENY "add a testing section"; generate#2 (note in prompt) → text; review#2 → PERMIT
- Expect visited: [generate, review, generate#2, review#2]
- Expect gates: [review: DENY → cycle back, review#2: PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S3 — Budget used exactly: approved on the third pass
- Inputs: as S1
- Scripted: review#1 DENY; review#2 DENY; generate#3; review#3 PERMIT
- Expect visited: [generate, review, generate#2, review#2, generate#3, review#3]
- Expect gates: [DENY, DENY, PERMIT]
- Expect terminal: workflow_complete (verdict pass)

### S4 — Sent back with no redo left
- Inputs: as S1
- Scripted: review#1, #2, #3 → DENY
- Expect visited: [generate, review, generate#2, review#2, generate#3, review#3]
- Expect gates: [DENY, DENY, DENY → no redo left]
- Expect terminal: escalated:review

### S5 — Person cannot decide
- Inputs: as S1
- Scripted: review → INDETERMINATE
- Expect visited: [generate, review]
- Expect gates: [review: INDETERMINATE]
- Expect terminal: escalated:review

### S6 — Abandoned
- Inputs: as S1
- Scripted: review → ABANDON (brief gate)
- Expect visited: [generate, review]
- Expect gates: [review: ABANDON]
- Expect terminal: cancelled (run stopped by host)

### S7 — Stored output
- Inputs: as S1 with output mode `stored`
- Scripted: review → PERMIT
- Expect visited: [generate, review]
- Expect gates: [review: PERMIT]
- Expect terminal: workflow_complete (verdict pass; kept by the service, no pull request)

### S8 — Agent keeps failing to write
- Inputs: as S1
- Scripted: generate → failed ×3
- Expect visited: [generate (attempts 1–3)]
- Expect gates: []
- Expect terminal: escalated:generate

## Ambiguities for the process owner
- `review` is a required input of `generate`, but it has no value on the first pass; the step escapes the starvation check only because its other inputs are non-empty (`resolve_next.py:171-203`). Effectively optional, declared required.
- The loop is a guard inside a transition string; its budget (`max-cycles`) is a run input seeded by `processes.py`, not part of the workflow. A run started without it gets the engine default of 2 passes.
- ABANDON exists only in the brief's vocabulary and maps to stopping the run; the workflow's gate vocabulary is PERMIT/DENY/INDETERMINATE. INDETERMINATE cannot be sent through the brief gate engine at all.
- After a REVISE with no redo left, the brief is set back to `drafting` (`gate_engine.py:245-248`) while the run has escalated — the two records disagree.
- `review` declares output `approval`, but the gate records `{decision, decided_by, note}` under its node; which key a consumer reads is unstated.
- Terminal verdict is derived (`pass`) rather than declared; escalation is an answer kind, not a named run verdict.
- The gate kind is unstated and defaults to APPROVAL (`human_gate.py:52-66`).
