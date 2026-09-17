# WP-02 — Execution engine: permission-first, durable, resumable

**Follows:** WP-01 (definition model, schemas and validator) — "Nothing executes yet" was that
work package's explicit boundary; this one crosses it.
**Spec:** `docs/spec/process-definition.md` §7 (nodes), §9.2 (depth), §10 (permission and controls),
§12 (engine semantics). **Needs:** the `definition/` package built in WP-01 (unmodified).

## Why this shape

Reconciling the new v1 format against the two DAG-compiler paths already in `compiler/`
(`dag_parser.py`→`outcome_compiler.py` and `graph_dsl.py`→`graph_compiler.py`) found the two
disagree with each other on node-type vocabulary and dict shape, and only the `step` node type of
either is exercise-tested. Bending either to fit the spec costs more than it saves. Three of their
mechanics ARE reusable and are reused here rather than rebuilt: LangGraph's `interrupt()` /
`Command(resume=...)` (gate pause/resume), `Send()` (fan-out — not in this work package's scope,
kept for WP-03), and `RetryPolicy` paired with the existing `TransientPortError` /
`PermanentPortError` split (§12.4). `compiler/` itself is not modified (CLAUDE.md).

## Outcome

A validated `definition.Process` runs to completion through the spec's own stateless contract —
`next(run, scope)` / `report(...)` / `decide(...)` (§12.1) — for `STEP`, `ROUTE` and `GATE` nodes,
with permission checked before every dispatch (§10.1), every attempt durably recorded (§12.2),
every `MUTATION`/`SIDE_EFFECT` step claimed under a lease (§12.3), and every loop budget enforced
from those records rather than from memory (§7.3). `PARALLEL`/`JOIN`/`FOR_EACH` (§7.4–7.5),
process-calls (§9), triggers (§11) and templates (§13) follow in WP-03.

## Scope

1. **`domain/ports/policy.py`** — `PolicyPort` (§10.1): asks whether an acting identity holds a
   named permission, returning ADR-028's `PERMIT | DENY | INDETERMINATE`. A stub adapter, no
   `sulis.*` import — this is the seam ADR-022 names as missing from the published engine.
2. **`domain/ports/records.py`** — write-once attempt records keyed by `(run, scope, node,
   attempt)` (§12.2): inputs used, output, control results, verdict or error, who/what performed
   it, start/end times. A second write to the same key is refused, not overwritten.
3. **`domain/ports/claims.py`** — leases for `MUTATION`/`SIDE_EFFECT` steps (§12.3), under the same
   write-once guard: claim, renew, a second caller told the claim is held, an expired claim may be
   taken over and the takeover logged.
4. **`engine/steps.py`** — `STEP` execution: dispatch via the existing `ToolDispatchPort`,
   controls-after-every-step with `repair`/`on_control_fail` (§10.2), `TRANSIENT` retry /
   `PERMANENT` → `on_error` (§12.4).
5. **`engine/routes.py`** — `ROUTE` execution: evaluates `when` via WP-01's `expressions.evaluate`;
   no match with no `otherwise` **refuses at validation time already (V6)** — this PR's job is to
   make the runtime path fail closed too if it is ever reached, rather than defaulting to the
   first option the way `compiler/nodes/routing.py` does today.
6. **`engine/gates.py`** — `GATE` execution: deciders asked in order (`policy`/`agent`/`person`),
   `PERMIT`/`DENY`/`INDETERMINATE` vocabulary, the `decision@1` evidence checker and
   no-deciding-on-your-own-work check (both already written in WP-01's `checkers.py`, unwired
   until now), provenance recorded per decider asked. Built on `interrupt()` /
   `Command(resume=...)`.
7. **`engine/run.py`** — `next(run, scope)` / `report(...)` / `decide(...)` (§12.1): resolves
   `process@version`, recompiles the LangGraph graph (cheap, deterministic — the same shape
   `OutcomeGraphCompiler.compile()` already proves), resumes via a durable checkpointer keyed on
   `run`. Nothing held in memory between calls — the property a fresh-process resume test in A5
   proves rather than asserts.
8. **Loop budgets** (§7.3): a durable counter per loop (default name `<from>-><to>`), rebuilt from
   records — not an in-process variable — with `on_exhausted` routing.

## Out of scope

`PARALLEL` / `JOIN` / `FOR_EACH` (§7.4–7.5), calling a process (§9), triggers (§11), templates
(§13), observers (§12.5), any change to `compiler/`, releases.

## Acceptance criteria

Each is a test.

- **A1.** A `STEP` whose Tool returns `PERMANENT` fails to `on_error` without retry; one that
  returns `TRANSIENT` retries up to `retry.max` then takes `on_error`.
- **A2.** A `ROUTE` with no matching option and no `otherwise` — reachable only because a fixture
  deliberately bypasses V6 — refuses at runtime rather than silently taking the first option.
- **A3.** A `GATE` whose only agent decider reviewed its own output counts as `INDETERMINATE`,
  never `PERMIT`, even when the agent's own answer says `PERMIT`.
- **A4.** A `MUTATION` step retried after an unclean resume does not run twice: the second attempt
  observes the first's claim and is told it is already held (or, past lease expiry, logs the
  takeover) rather than dispatching again.
- **A5.** A run started by one process and resumed by a second process that shares no memory with
  the first (a fresh `next()` call against only the durable store) reaches the same next step —
  proving the stateless contract rather than asserting it.
- **A6.** A permission denial is recorded once as `FORBIDDEN`, takes `on_forbidden`, and is never
  retried.
- **A7.** `pytest`, `ruff` and `mypy` pass on Python 3.10–3.12 in CI for every new module (CI scope
  extended from `definition/` to also cover `engine/` and the new `domain/ports/` files, in the
  PR that introduces each).

## Suggested PR sequence

1. `PolicyPort` + `RecordsPort` + `ClaimsPort`: ports and stub adapters, contract tests only — no
   execution yet.
2. `STEP` execution (A1) — permission check, dispatch, controls/repair, retry/error classes.
3. `ROUTE` execution + durable loop budgets (A2).
4. `GATE` execution (A3) — deciders, vocabulary, evidence + separation-of-duty checks, provenance.
5. `next`/`report`/`decide` (§12.1) + claims (A4, A5, A6) — the crash-resume proof.

Each PR carries its own principal summary and run record (see `CLAUDE.md`).

## If the spec is wrong or silent

Do not resolve it in code. Propose the spec change in the PR, keep the code to the spec as
written, and flag it in the run record.
