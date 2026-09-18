# Author a Tool — fd

Source: fd-product-architecture/processes/author-tool.process.yaml
Purpose: Check a draft Tool against the register's decidable authoring rules, then either run the registered Tool's own evals or propose a corrected document.
Use cases: UC-IN-TYPED, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-STOP-NAMED, UC-TOOL-KINDS, UC-TOOL-RUNNER, UC-OUT-TYPED, UC-MECHANISM

## Steps
| Path | Step | Kind (agent/tool/human/process-call/decide) | Does | Reads → Writes |
|---|---|---|---|---|
| — | (no framing, no entry_decision) | — | Single path; runs directly (spec §1). | — |
| draft-and-prove | check-draft | tool (`check-tool-draft`) + decide on `verified_by` | Validates the draft against the Tool schema and decidable completeness rules. | `draft` → `draft_conformant` (bool), `draft_violations`; produces `conformance_report` |
| draft-and-prove | evaluate | tool (`run-tool-eval`) | Executes the registered Tool once per acceptance example of its Scenario and judges each output. | `subject`, `subject_scenario` → `eval_results`; produces `eval_result` |
| draft-and-prove | propose-fix | tool (`propose-tool-fix`, model-backed) | Proposes the whole corrected Tool document, naming each violation addressed. | `draft`, `draft_violations` → `tool_fix_proposal` |

## Routes as declared
- Entry: none; exactly one path `draft-and-prove`, `start: check-draft`.
- `check-draft`: `verified_by: draft_conformant` → condition on state `draft_conformant`: truthy → `next: [evaluate]`; falsy → `on_fail_goto: propose-fix`.
  - A missing `draft_conformant` key is treated as falsy (fail): declared only in executor, `executor/service_layer/compile_generic.py:213-224` (`_branch_on`). The schema says "when the key is falsy after the step runs, route to on_fail_goto" (`schemas/process.schema.json:468-472`), so absence-as-fail is consistent but not stated.
- `evaluate`: `next: [end]` → terminal (output `eval_result`).
- `propose-fix`: `next: [end]` → terminal (output `tool_fix_proposal`). Deliberately no loop back to `check-draft` (comment in definition: no auto-repair loop).
- Loops: none. Budgets: none.
- Terminal verdict names: UNSTATED (both endings are plain `end`; the output form distinguishes them).
- Approval gates, `methodology_ref`, recursion: none.

## Scenarios
### S1 — Conformant draft, evals run
- Inputs: `draft` = a Tool YAML satisfying every decidable rule; `subject` = `{kind: tool, ref: my-tool}`; `subject_scenario` = `{kind: scenario, ref: my-tool-acceptance}`
- Scripted: check-draft → `{draft_conformant: true, draft_violations: []}`; evaluate → `eval_results: [2 × passed]`
- Expect visited: [check-draft, evaluate]
- Expect gates: []
- Expect terminal: end (output `eval_result`)

### S2 — Non-conformant draft, fix proposed
- Inputs: `draft` = a Tool with a non-deterministic mechanism and no controls; `subject`, `subject_scenario` absent
- Scripted: check-draft → `{draft_conformant: false, draft_violations: ["controls required for non-deterministic mechanism"]}`; propose-fix → `tool_fix_proposal` naming that violation
- Expect visited: [check-draft, propose-fix]
- Expect gates: []
- Expect terminal: end (output `tool_fix_proposal`; `evaluate` never runs)

### S3 — Checker writes no verdict key
- Inputs: `draft` = any
- Scripted: check-draft → output without `draft_conformant` (Tool returned an unmapped key)
- Expect visited: [check-draft, propose-fix]
- Expect gates: []
- Expect terminal: end (output `tool_fix_proposal`) — absence treated as fail (declared only in executor)

### S4 — Conformant draft, an acceptance example cannot execute
- Inputs: as S1
- Scripted: check-draft → `draft_conformant: true`; evaluate → `eval_results: [passed, not-verified]`
- Expect visited: [check-draft, evaluate]
- Expect gates: []
- Expect terminal: end (output `eval_result`, one row `not-verified`, never skipped)

## Ambiguities for the process owner
- `subject` and `subject_scenario` are declared as inputs with no `required` flag, yet `evaluate` cannot run without them; the non-conformant path (S2) needs neither. Required-ness per path is unstated.
- The Tool is "once registered" before `evaluate` — nothing in the process registers the draft between `check-draft` and `evaluate`. Whether a host must register it, or `evaluate` runs against the draft, is unstated.
- `propose-fix` verification ("the proposed document passes check-tool-draft") has no `verified_by`/`on_fail_goto`; spec §6 says a failed verification with no failure edge MUST halt, but the definition deliberately ends at `end`. What a failed proposal's terminal is: UNSTATED.
- Absence of `draft_conformant` routes to fail: declared only in executor (`compile_generic.py:213-224`).
- The executor only compiles this process generically in tests: `compile_process` refuses it at run time because `author-tool` is not in `_GENERIC_STATE` (`executor/service_layer/compile.py:888`, `:939-943`). The definition is runnable in principle; the host path is missing.
- Terminal verdict names are unstated; two different outputs end on the same `end`.
