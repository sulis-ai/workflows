# Changelog

All notable changes to `sulis-workflows`. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: [SemVer](https://semver.org/). A release is a `vX.Y.Z` git tag.

## [Unreleased]

### Added
- **D44 (WP-04 Part 1):** `mechanism.kind: EXTERNAL` is now dispatched by the engine, closing the
  `EXTERNAL` half of D34's own refusal. A new `ExternalToolPort` (`domain/ports/external_tool.py`),
  mirroring `CodeToolPort`'s own shape exactly, is wired into `attempt_step` alongside
  `CodeToolPort` — the two share every surrounding rule (permission, precondition, inputs, error
  classification, control-checking), differing only in which port's `call(ref, ...)` performs the
  dispatch. `V17` no longer refuses `EXTERNAL`; `TOOL` (composite) remains refused until WP-04
  Part 2.
- **D43 (WP-05 Part 3), new rule `V19`:** the fuller half of spec §9.1's "the calling step MUST
  route every value of `ending`" is now provable, not just documented as unimplemented (D36).
  A `PROCESS`-mechanism call's own captured ending must be written to an `enum[...]`-typed
  channel, and a reachable `ROUTE` must test every value the call can produce (or cover the rest
  with `otherwise`) — closing the gap D40 left open one hop further out. Found and fixed a real,
  previously-undetected bug in `examples/recursive-refinement/` while building this: two steps
  captured a recursive call's own ending but never routed on it, silently reporting a denied or
  failed recursive branch as the whole work tree completing successfully.
- **D42 (WP-05 Part 2):** `ClaimsPort.renew` is now reachable through a new public call,
  `heartbeat(run, scope, node)` — a still-in-progress `MUTATION`/`SIDE_EFFECT` step's hand-off
  can have its lease genuinely extended, closing the "no renewal for a hand-off slower than the
  lease" gap D37 left open. Fixed a real, previously-latent bug found while building this:
  `StubClaimsAdapter.renew` used to unconditionally overwrite its own store with whatever the
  caller's own `claim` argument said, never checking whether that caller still actually held it —
  a claim already taken over by a second caller could still be "renewed" by the first, silently
  defeating §12.3's own at-most-once guarantee. `renew` now fails with `TAKEN_OVER` (reusing
  `acquire`'s own status) when the caller no longer holds the claim or it has already expired.
- **D41 (WP-05 Part 1):** `kind: INPUT` gates (spec §7.6) are now implemented, closing D26's
  outright refusal. A `person` decider answers via a new `decide(..., value=...)` parameter
  (checked against the gate's own `answer_type` before being recorded); `policy`/`agent` deciders
  are still asked (their own vote recorded for provenance) but can never actually answer one —
  neither `PolicyPort.evaluate_policy` nor an agent's own `decision@1` profile has anywhere to
  carry a typed value — and always pass on to the next decider, exactly as an ordinary
  `INDETERMINATE` outcome already does. V9 drops D26's blanket refusal for real shape checks
  (`answer_type`, `answer_into`, an `ANSWERED` route present; `answer_into` targeting a
  non-`REPLACE` channel refused, mirroring `note_into`'s own D27 check).

### Fixed
- **D40:** a `PROCESS`-mechanism call whose calling STEP never captured the synthesised `ending`
  output into state could have its child's own `FAILED`/`STOPPED` ending silently masked as the
  step's own plain `SUCCESS` — nothing downstream could ever read what the child actually did.
  This is the unambiguous half of spec §9.1's own "the calling step MUST route every value of
  `ending`" (D36 found the fuller requirement genuinely unimplemented and left it that way, but
  the field is always the literal, engine-hardcoded key `"ending"`, not something to guess at).
  **V10** now refuses a call whose `out:` doesn't map it; `_advance_process_call` refuses the same
  shape at runtime.
- **D39:** spec §9.1's own worked example used `mechanism.inputs: { brief: brief }` (a bare,
  unqualified name) — the only place in this entire document, or in the real corpus, that a
  `mechanism.inputs` path is not fully qualified (`state.*`/`inputs.*`/`host.*`/`steps.*`, the
  same as every `in:`/`out:`/`if:` path elsewhere). Confirmed, by actually driving this exact
  example through `next()`/`report()` for the first time, that the bare form silently resolves to
  `None` against the real engine (`_resolve_call_inputs` reads `mechanism.inputs` straight off the
  calling process's own run state; the calling STEP's own `in:` mapping is never consulted for a
  `PROCESS`-mechanism dispatch). Spec §9.1 now shows `{ brief: state.brief }`, matching the
  convention `tests/engine/test_run.py`'s own `PROCESS`-mechanism coverage already tests; a new
  bullet states the rule plainly. `examples/recursive-refinement/`'s own two affected Tools are
  fixed the same way.
- **V8 loop-budget checking, and `explain`'s own loop listing, now see a loop declared on a
  ROUTE's `otherwise` clause** — both only ever walked a `RouteNode`'s `when` options for `.loop`
  before, silently missing a bad-but-conformant budget (or `counts: FAILURES`) declared on
  `otherwise` instead (a real, legal shape: `otherwise` is itself a `RouteTarget` with its own
  `loop` field). Found while building `examples/recursive-refinement/`, whose own completeness
  gate loops back via `otherwise`.
- **D38:** `invalidates` (spec §7.3) was accepted by the schema and model but never read anywhere
  the engine resolves state — a definition declaring it had the declaration silently ignored. Now
  refused at validation (**V18**, new) and engine runtime, rather than implemented (doing so
  correctly needs new state-tracking machinery in the same replay-position territory that produced
  D19-D23/D27, and the spec names no mechanism for "a superseded output"; see D38's own proposed
  spec clarification). Also corrects a claim that had propagated unverified across several prior
  run records — Appendix A's own worked example does not declare `invalidates`; only this spec
  document's own illustrative §7.2 snippet did, now removed to match. Fixes a real, related
  replay-correctness bug found while investigating: `_advance_route`'s own replay branch dropped
  `invalidates` when reconstructing an already-recorded route decision (correct on the call that
  first records it, silently wrong on every later call that replays it) — the same "correct once,
  silently lost on replay" shape as D19/D27.
- **D37:** `ctx.claims.acquire` (§12.3's at-most-once claim/lease guard) was only ever called before
  an inline `CODE` dispatch — a hand-off `SKILL`-mechanism `MUTATION`/`SIDE_EFFECT` Tool acquired no
  claim at all, so a second caller racing in during the hand-off got a fresh `TOOL_STEP` instead of
  `STEP_RUNNING`. Now shared by both dispatch paths via a new `_claim_if_effectful` helper.
  `ClaimsPort.renew` remains genuinely never called anywhere — implementing it needs a new public
  API surface (a heartbeat-style call) this pass does not invent; see D37's own proposed spec
  clarification.
- **D36:** `V10`'s `result.endings`-coverage check only ever ran for a `ref`'d Process call —
  `_resolve(registry, "PROCESS", None)` silently no-ops for an inline `process:` call's `None`
  ref, so an inline body missing one of its own declared endings from `result.endings` passed with
  zero findings. Now checked for both. Spec §9.1's separate "the calling step MUST route every
  value of `ending`" requirement is verified genuinely unimplemented and left that way — closing it
  would mean guessing which `Tool.output` field carries the ending value, which nothing in the spec
  states explicitly; see D36's own proposed spec clarifications.
- **D35:** an inline `PROCESS` mechanism's own body (`mechanism.process`, spec §9.1, D18) was never
  checked by any validator rule — a bad-but-conformant inline body (unreachable node, undeclared
  state channel, non-exhaustive route, undeclared `tool:` reference, ...) passed with zero findings
  and only surfaced as an uncaught `EngineRefusal` the first time a run reached it. Now checked by
  the same rules (V2, V4-V9, V11-V14, V16) a top-level Process document is, reused directly against
  a synthetic wrapper. Found and fixed a real instance in this repo's own spec-mirrored worked
  example: `state.current`/`state.survived` were read/written but never declared.
- **D34:** a `mechanism.kind: EXTERNAL` or `TOOL` (composite) Tool was silently dispatched as if it
  were a `SKILL` — handed off to the caller's agent session as an ordinary `TOOL_STEP` (for
  `TOOL`, one with no instructions at all, since this kind has no `ref`) — though spec §12.1
  states both belong on the engine-run side of the dispatch split, alongside `CODE`. Now refused
  at validation (**V17**, new) and engine runtime, rather than implemented (both would require
  inventing spec-silent operational details — a host-adapter port shape for `EXTERNAL`, "shared
  values" semantics for `TOOL`-composite — not guessed at here; see D34's own proposed spec
  clarifications).
- **D33:** `loop.counts` (`PASSES`/`FAILURES`, spec §7.3/§15) was accepted, parsed, and never
  read — every loop take counted toward its budget regardless of verdict, exactly `PASSES`
  semantics, whatever `counts` said. Now implemented for `GATE` loops (a take counts only when
  the resolving verdict is `DENY` — unambiguous, since `DECIDED` only ever carries `PERMIT`/
  `DENY`) and refused, at validation (**V8**) and engine runtime, for `ROUTE` loops, where a
  `when` branch has no engine-visible "because a check failed" signal to read.
- **D32:** `note_into` (D24) only ever captured a `person` decider's own `note` — a `policy`- or
  `agent`-decided verdict left its declared target channel untouched, silently dropping the
  decider's own reasoning exactly like D24's original bug, just for two of the three decider
  kinds. `_state_with_note` now also accepts a decider's `rationale`; a policy decider's own
  `rationale` (computed but never persisted) is now recorded in its attempt record at all.
- **D31:** `retry.backoff_seconds` (spec §7.1/§15, "the starting delay before exponential
  backoff") was accepted, parsed, and otherwise completely unused — a `TRANSIENT` retry
  redispatched immediately, back-to-back, regardless of any declared or defaulted backoff.
  `_advance_step` now waits `backoff_seconds * 2^(retry_number-1)` before each retry dispatch;
  `retry.max` (already correctly enforced) is unaffected. No ceiling is applied — the spec states
  none.
- **D30:** a second caller racing to record the same attempt (two `next()`/`report()`/`decide()`
  calls replaying from the same durable position, both computing the identical next
  `AttemptKey` for a node neither has recorded yet) crashed with an uncaught `DuplicateAttempt`
  instead of completing normally — nothing in `engine/run.py` caught the write-once guard's own
  exception (spec §12.2) at any of its 9 `record_attempt` call sites. All 9 now go through one
  shared `_record_attempt` helper that swallows `DuplicateAttempt`, the write-side counterpart of
  the same "same backend, same answer" replay property §12.1 already requires of reads.
- **D29:** an attempt record's `inputs` (spec §12.2, "inputs used") was always written `{}`, for
  every node type. Fixed where it was cheap and exact: `_record_step_result` (the shared recorder
  for every `CODE`-mechanism dispatch and every STEP-node failure recorded before a hand-off) now
  carries the STEP's real resolved inputs. A `report()`-completed hand-off's own SUCCESS/ERROR
  record, and every `ROUTE`/`skip()`/GATE-decider record, remain `{}` — a verified, deliberately
  unfixed gap needing a design decision named in D29, not guessed at.
- **D27:** a gate's `note_into` (D24, v0.12.2) crashed with an uncaught `ReducerMismatch` when its
  target channel's reducer was `APPEND` — exactly the shape both the spec's §7.6 example and
  Appendix A's own worked example used. The engine recomputes and re-applies a gate's note on
  every replay pass, which is safe only for an idempotent reducer (`REPLACE`); `APPEND` would have
  silently accumulated the same note again on every replay even once the crash was fixed. Now
  refused at both validation (**V9**) and engine runtime, the same defence-in-depth `kind: INPUT`
  (D26) already has. Both spec worked examples corrected to a `REPLACE` `note` channel.
- **D28:** a process's own `defaults.loop_budget` was silently ignored at runtime for any loop
  that omitted its own `budget:` — both `_advance_route` and `_advance_gate` hardcoded
  `process_default_budget=None` when calling `check_loop_budget`, so such a loop always used the
  format default (10) instead, while `explain` (`cli.py`) correctly reported the process's own
  default. Both call sites now read `process.defaults.loop_budget`.
- **D25:** the spec's own Appendix A worked example (and its mirrored fixture) declared
  `sign-off.person_required_when: state.confidence == "INSUFFICIENT"` — a condition that could
  never actually evaluate true in a real run, since `honest-stop` already diverts `INSUFFICIENT`
  away before `sign-off` is ever reached. Corrected to `state.confidence == "PARTIAL"`, a value
  `sign-off` is actually reached with; the person-required decider path (previously untested end
  to end, since it was unreachable) now has a regression test.
- **`GATE kind: INPUT` refused cleanly instead of crashing at runtime (D26):** `kind: INPUT` gates
  (spec §7.6) validated but then failed at runtime with a confusing
  `"no route declared for verdict 'PERMIT'"`, since the engine never implemented them. Now
  refused outright, with a clear reason, at validation time (**V9**) and — in case validation is
  bypassed — at engine runtime too, the same defence-in-depth `PARALLEL`/`JOIN`/`FOR_EACH`
  already have. See D26 (`docs/spec/process-definition.md` §18) for the open spec questions real
  `INPUT` support would need answered first.

### Docs
- Corrected stale claims: `engine/run.py`'s module docstring said state writes support only the
  `REPLACE` reducer (D19 implemented `MERGE`/`APPEND`/`UPSERT_BY_ID` without updating this line);
  `engine/__init__.py` and `docs/work-packages/WP-02-execution-engine.md` said the engine "targets
  LangGraph directly" and resumes via a LangGraph checkpointer — `engine/` imports no `langgraph`
  anywhere and resumes by replaying durable attempt records instead (WP-03a verification pass).

## [0.12.2] — 2026-09-20

### Fixed — four faults found by building a consumer on v0.12.1, each with its own regression test
- **Packaging:** the wheel shipped without `definition/schema/` and `definition/builtin/`, so an
  installed copy could not load any definition at all — every test in this repository passes
  against the source tree, where the data is always present. `pyproject.toml` now declares the
  package data, and a new CI job (`the wheel carries its data`) builds the wheel, installs it
  alone and reads the data back; `tests/test_the_package_ships_its_definition_data.py` is what it
  runs. This is the only check that can catch the class of fault, and it is why v0.12.0 and
  v0.12.1 shipped broken.
- **D24, `note_into`:** a decider's send-back note never reached the attempt it sent work back to.
  The field was in the schema, the model and the validator, and the reducer dropped it. It is now
  written onto the decision's replay state (latest note wins) and resolves as an input to the step
  the loop returns to; four internal `_advance_gate` call sites gained the scope definition they
  need to do it. Regression:
  `tests/engine/test_a_send_back_note_reaches_the_next_attempt.py`. Recorded as D24 in
  `docs/spec/process-definition.md` §18.
- **PEP 561:** the package shipped no `py.typed`, so a typed consumer saw every public name as
  `Any` and its own type checking silently weakened. Adding the marker then surfaced a genuine
  port mismatch (below).
- **`ToolDispatchPort`:** the port declared a workspace value object for paths and a bare mapping
  for arguments, while every caller passes a string and a string-keyed mapping. The port now
  declares what its callers actually pass.

### Changed
- CI: the lint, format and type checks run in the job that installs the development extra. They
  had been appended to the wheel job, which installs the built wheel alone, so they failed on a
  missing module rather than on the code — and had not been running at all on the branches above.

## [0.12.1] — 2026-09-20

### Fixed — five engine correctness bugs found by actually running processes, not just validating them (D19–D23)
- **D19:** `MERGE`/`APPEND`/`UPSERT_BY_ID` state-channel reducers (spec §2.3) were never implemented;
  a step writing to one crashed `report()` instead of failing that one attempt cleanly. New
  validator rule **V16** (an `UPSERT_BY_ID` channel must declare `key`).
- **D20, D21, D22:** a loop body spanning more than one hand-off could get permanently stuck
  (`STEP`), silently skip a node's fresh re-ask (`ROUTE`), or silently discard a later, genuinely
  different decider verdict in favour of an earlier stale one (`GATE`) — three instances of the
  same replay-baseline miscount, found and fixed one node type at a time.
- **D23:** `decide()` (the `person`-decider half of §12.1) had a separate, untouched copy of the
  same miscount — a reviewer who sent work back on a `GATE` could never approve it afterwards,
  wrongly refused as unauthorized on the second decision. `decide()` now drives through the same
  already-correct replay `report()`'s own agent-decider path uses, rather than recomputing its
  position independently.
- New end-to-end regression suite (`tests/engine/test_grounded_inquiry_e2e.py`) driving spec
  Appendix A's own worked example through the real engine for the first time.
- Decisions D19–D23 recorded in `docs/spec/process-definition.md` §18.

## [0.12.0] — 2026-09-18

### Added — the v1 process-definition format and its execution engine (`definition/`, `engine/`)
- A new system alongside `compiler/` (untouched, still the LangGraph `Workflow`-entity path): a
  declarative process-definition format (`docs/spec/process-definition.md`, v1) with its own JSON
  Schemas, a typed model, a YAML/JSON loader, an `id@version` registry, an expression language,
  a validator (rules V1–V15, each with an accepted and a refused fixture), built-in checkers, and
  a CLI (`sulis-workflows validate|explain`).
- A real, tested execution engine on top of it: `next()` / `report()` / `decide()` / `skip()`
  (spec §12.1) drive a `Process` through `STEP` (deterministic `CODE` dispatch, `SKILL`
  hand-off), `ROUTE`, and `GATE` (policy/agent/person deciders) nodes — permission checked before
  every dispatch, every attempt durably recorded, `MUTATION`/`SIDE_EFFECT` steps claimed under a
  lease, loop budgets enforced from records rather than memory.
- **Calling a process** (spec §9): a `PROCESS`-mechanism STEP recursively drives a child scope —
  either a separately named, independently governed process (`ref:`) or a small sequence
  declared inline just for that Tool (`process:`, D18). A hand-off inside a nested call bubbles up
  carrying its own scope and resumes the same way a top-level one does. Depth-limited (default
  4); a called process with no permission is refused before it is ever entered.
- New ports: `PolicyPort`, `RecordsPort`, `ClaimsPort` (`domain/ports/`), each with a stub
  adapter and contract tests.
- **Known gaps, refused rather than silently mishandled:** `PARALLEL` / `JOIN` / `FOR_EACH`,
  triggers, and templates are not yet executable; a process call's `path` override (forcing a
  called process's first branch) is spec-valid but not yet supported by the engine.

## [0.11.0] — 2026-08-13

### Added — the `route_decider` node type (real conditional branching)
- `VALID_NODE_TYPES` declared `"route_decider"` since `dag_parser.py`'s first cut, but nothing
  ever implemented it: `NodeResolver` had no branch for it, `_wire_edges` only recognised
  `"routing"`, and GV-01's cycle check didn't count it as a conditional exit. A `route_decider`
  node is a step node (real dispatch, writes its own `step_outputs[node.id]`) whose computed
  output `_wire_edges` then reads back to pick a conditional edge.
- Closes the gap blocking real DAG-mode branching on a Workflow's own guarded transitions.
- 4 new tests; full existing suite (29) green.

## [0.10.0] — 2026-08-01

### Added — `ToolDispatchPort.invoke` sees this run's own accumulated `step_outputs`
- `invoke(primitive, args, *, sandbox_root, platform_id, run_id, step_outputs=None)` — a new
  optional, additive keyword. `compiler/nodes/step.py`'s `step_fn` already receives the full
  LangGraph `state` (including `step_outputs`); this just threads it past the tenancy trio it
  already forwards, into `invoke` itself. Every existing adapter that ignores the new kwarg
  keeps working unchanged (`StubToolDispatchAdapter` now records + echoes it back for test
  assertions).
- **Why:** found live, driving a real two-level-deep `workflow_dispatch` recursion (a
  Workflow's own step dispatching a second Workflow) for the first time — the second hop had
  no way to see what the FIRST hop had actually produced by that point (e.g. a
  gather-context step's real output), only the outermost run's original inputs, which a
  consumer-side adapter (`SubworkflowDispatch`) had already threaded down via
  `set_run_inputs`. That mechanism is necessarily shallow — set once, inherited unchanged by
  every further recursion — since the engine never gave the adapter anything richer to work
  from. `step_outputs` closes that gap without changing the engine's execution model at all;
  a `workflow_dispatch`-kind adapter can now seed a nested sub-run from the CALLING run's own
  latest output, not just the original top-level inputs.

## [0.9.0] — 2026-07-21

### Added — retry/resilience, wired to two dead extension points already in the schema
- `DAGNode.retry` (`compiler/dag_parser.py`) was parsed from every node's YAML since v0.1.0
  and never consumed anywhere -- a dead field. Now wired to LangGraph's own native
  `RetryPolicy` (`add_node(..., retry_policy=...)`) via the new `compiler/node_retry.py`.
  LangGraph re-invokes a node's ENTIRE coroutine on a retryable exception -- the same
  "whole-unit re-execution + exponential backoff" convention Temporal (Activity retries)
  and AWS Step Functions (Retry/Catch) both use.
- `content`/`step` nodes get a REAL DEFAULT retry policy (`max_attempts=3`) even with no
  explicit `retry` declared -- every consumer benefits, not just ones who remember to opt
  in. `gate` nodes (human interrupts) get none; an explicit `retry: {max_attempts: 0}`
  opts any node out.
- New shared error vocabulary (`domain/errors.py`): `PortError` -> `TransientPortError` /
  `PermanentPortError`. Generalizes what was storage-only (`TransientStorageError`/
  `PermanentStorageError` in `ports/content_storage.py` -- the only error classification
  anywhere in the engine, referencing a "tenacity policy" that was never implemented) so
  `LLMPort`/`ToolDispatchPort` adapters (which documented ZERO exceptions before this) can
  opt into the same retry treatment. `TransientStorageError`/`PermanentStorageError` are
  now subclasses of the new base -- existing `isinstance` call sites are unaffected.
- Found live, not speculative: a consumer (brain-runtime) proving a real ~75-minute nested
  Workflow run hit a one-off transient `claude` CLI failure on its final step -- with no
  retry anywhere, the whole run was lost. `RetryPolicy`'s default `retry_on` classification
  (5xx/connection errors yes; `ValueError`/`OSError`/etc no) is extended by the new
  `TransientPortError`/`PermanentPortError` check so an adapter's own classification wins.
- Scope, named plainly: this covers failures INSIDE a node (a port call). The engine ships
  no runner (`graph.ainvoke()` is always the consumer's call) -- a consumer reporting a
  run's terminal state to ITS OWN infrastructure after the run returns is structurally
  outside the graph and outside this fix's reach.
- Backward compatible: a node with no `retry` declared and a type outside `{content, step}`
  behaves exactly as before. Proven by the full existing suite passing unchanged plus 5 new
  tests (`tests/test_node_retry.py`) exercising real retry-then-succeed and
  permanent-fails-immediately through the actual compiler + real LangGraph execution, not
  mocked.

## [0.8.0] — 2026-07-21

### Added — `LLMRequest.system_prompt` (a real system-prompt channel for content nodes)
- `LLMRequest` gains an optional `system_prompt: str | None = None`. A content node's
  compiled config can now carry compile-time-known static context (e.g. a Step author's
  own instructions) SEPARATELY from `prompt` (the run's dynamic, `step_outputs`-resolved
  value) — `make_content_node(..., system_prompt=...)` threads it through, and
  `NodeResolver` reads it from `node.config["system_prompt"]`.
- Found live, not speculative: a consumer (brain-runtime) compiling a real canonical
  Workflow's Steps into content nodes discovered the engine had NO way to use a Step's
  own authored `agent_instructions` at all — every LLM call got only the raw upstream
  text, producing generic, context-free output regardless of how rich the Step's own
  instructions were. `system_prompt` is the missing channel.
- `StubLLMAdapter.complete` reflects `system_prompt` in its echo (`[system:...] `
  prefix, only when set) so consumers can assert the wiring without a real adapter.
  `examples/anthropic_llm_adapter.py` maps it onto the Anthropic SDK's `system` param.
- Backward compatible: omitting `system_prompt` (the default) behaves exactly as before
  on every existing call site — proven by the full existing suite passing unchanged.

## [0.7.0] — 2026-06-17

### Added — generic `ToolDispatchPort.invoke` (richer tool coverage beyond the workspace trio)
- `ToolDispatchPort` gains `invoke(primitive, args, *, sandbox_root, platform_id, run_id) -> dict`
  — the escape hatch for primitives **beyond** the typed workspace trio (`read_file`/`glob`/
  `ripgrep`). A step whose spec names any other primitive (e.g. `subprocess`, `http_call`)
  routes through `invoke`; the engine stays transport-agnostic (it names the primitive + args),
  and the **adapter** owns how it executes. This is how a consumer's richer tool catalogue is
  supported without growing the engine's surface. An adapter with no `invoke` fails loud.
- `StubToolDispatchAdapter.invoke` returns a deterministic echo; `tests/test_adapters.py::
  test_step_dispatches_a_non_workspace_primitive_via_invoke` proves the routing + tenancy.

## [0.6.0] — 2026-06-16

### Fixed — live-execution tenancy now reaches the ports (NFR-11/21)
- Step + content nodes now thread the **running execution's identity** into every port
  call: `run_id` ← `state["execution_id"]`, `platform_id` ← `state["metadata"]["platform_id"]`
  (factory args still win if set). Before this, dispatched tool/LLM calls arrived with empty
  tenancy keys — the isolation/audit keys the ports mandate were silent at runtime. Caught by
  driving a **real filesystem tool adapter** against the published v0.5.0 (`/sulis:prove`):
  the glob found the right files but `run_id` reached the adapter empty. Now proven: the tests
  assert `observed_calls == [(platform_id, run_id)]` from the live run.

## [0.5.0] — 2026-06-16

### Added — step nodes now do REAL work (step → ToolDispatchPort)
- A `step` node whose spec names a `primitive` (`read_file` / `glob` / `ripgrep`) now
  **dispatches it through the injected `ToolDispatchPort`** — real workspace work — and the
  result lands in `step_outputs[node_id]` (was: load-spec-and-mark-completed, no dispatch).
  Same shape as the content node's `LLMPort` (DR-040): the engine depends on the Protocol;
  the runner injects the adapter. Proven by `tests/test_adapters.py::
  test_step_dispatches_a_tool_primitive_via_the_port` (drives `StubToolDispatchAdapter`,
  asserts the saved result + that tenancy reached the adapter).
- **`Adapters.sandbox_root`** — the path-traversal boundary (NFR-14) every dispatch carries,
  threaded from the bundle → resolver → step node. A primitive step with no injected
  `tool_dispatch` / no `sandbox_root` raises a clear `MissingAdapterError` at execution
  (fails loud, never a silent no-op).
- **Backward compatible:** a step with no `primitive` falls back to recording its resolved
  spec — pure step graphs compile + run unchanged (`test_step_without_a_primitive_*`).
- Step nodes are now **async** (they may `await` a port), consistent with content nodes.

### Still thin (honest)
- `fan_out`/`routing`/`while` → passthrough; `handler` → deferred (dispatch port).
- The step primitive set is the slice-1 surface (`read_file`/`glob`/`ripgrep`); richer
  primitives extend `_dispatch_primitive` behind the same port.

## [0.4.0] — 2026-06-16

### Fixed — content (LLM) workflows now RUN to completion (real work end-to-end)
- A content node now reads its prompt from / writes its response to the **`step_outputs`**
  channel (a merge-reducer field on `OFMGraphState`) instead of arbitrary top-level state keys
  (which the typed schema dropped). So an LLM workflow compiles **and runs to completion**: a
  step-node + content-node graph executes, the content node calls the LLM via the injected
  `LLMPort`, and the response lands in `step_outputs` (`tests/test_adapters.py::
  test_content_workflow_runs_to_completion`). This closes the `/sulis:prove` run-to-completion
  block for content workflows. `make_content_node` now takes the node id (records `completed_nodes`).

### Still thin (flagged by /sulis:prove — honest)
- **Step nodes don't do real work yet** — `make_step_node` loads the spec + marks completed; it
  does not dispatch via `ToolDispatchPort`. Wiring step → ToolDispatch is a *defined slice* (needs
  the step-spec → primitive mapping + `sandbox_root` threading), not the quick fix it first looked.
- `fan_out`/`routing`/`while` → passthrough; `handler` → deferred (dispatch port).

## [0.3.0] — 2026-06-16

### Added — the generic port mechanism (compile-level injection)
- **`Adapters` bundle** (`sulis_workflows.runtime.Adapters`) — one injection point for every
  port. A runner injects the adapters its placement needs (`Adapters(llm=…, content_storage=…,
  checkpointing=…)`); the engine threads them through `OutcomeGraphCompiler(spec_repo,
  adapters=…)` → the node resolver → each node, which resolves its port via
  `adapters.require("…")`. A missing port raises a clear **`MissingAdapterError`** (the port +
  the fix), never a crash. This is the seam both runners (server + client) use.
- **`content` node type** wired end-to-end: added to the DAG schema + the resolver, builds a
  content node bound to the injected `LLMPort`. A `content`-node graph compiles + runs against
  `StubLLMAdapter` with no LLM SDK present (`tests/test_adapters.py`).
- **Docs:** `docs/getting-started.md` (compile-and-run walkthrough for new developers) +
  `docs/ports.md` updated (the `Adapters` bundle is the injection seam).

### Deferred (remaining)
- Handler-node dispatch → a dispatch port (the last platform coupling).
- Extend `compile()`-time adapter resolution to the remaining node types (step → ToolDispatch, etc.).

## [0.2.0] — 2026-06-16

### Added — the port pattern, demonstrated end-to-end
- **Content nodes now consume the injected `LLMPort`** instead of importing the Anthropic SDK
  directly — closing one of the two deferred couplings. `make_content_node(..., llm=<LLMPort>)`
  calls `llm.complete(LLMRequest(...))`; the engine carries **no LLM-SDK dependency** (verified:
  all modules import + all tests pass with `anthropic` blocked).
- `tests/test_llm_port.py` — proves define → adapt → inject → invoke with `StubLLMAdapter` (no SDK,
  no network), incl. tenancy (`platform_id`/`run_id`) propagation through the port.
- `examples/anthropic_llm_adapter.py` — a real `LLMPort` adapter (consumer-side; imports `anthropic`
  *there*, not in the engine) showing how a runner provides a real LLM.
- `docs/ports.md` — the port pattern (define/adapt/inject/invoke), the port list, and the injection
  seam (node-level today; compile-level next).

### Deferred (remaining)
- **Handler-node dispatch** (`node_factory._resolve_handler`) → a dispatch port (still the one
  remaining platform coupling; not exercised by step-node graphs).
- **Compile-level adapter injection** — `compile()` threading an adapter bundle to the nodes it
  builds (today adapters are injected at the node factory).

## [0.1.0] — 2026-06-16

### Added
- **The engine core, extracted from the platform** (`apps/api/sulis/shared/workflows`) and proven
  standalone: `compiler/` (canonical DAG → LangGraph `StateGraph`) + the core `domain/` (models, the
  ~10 ports, signing, identity, state). Compiles a step-node graph with **zero platform dependency**
  (only `langgraph` + stdlib + the in-memory spec repo). 73 modules import clean; `compile()` proven by
  `tests/test_compile.py`.
- A no-op `span_context` (`_tracing.py`) so the engine carries no platform tracing dep; real tracing is
  an injected `ObservabilityPort` concern.

### Boundary (what's IN vs OUT — per DR-040)
- **IN (the engine):** the compiler + core domain + ports + the one pure action DTO the compiler needs
  (`kind_invocation`).
- **OUT (control plane / platform content, left in the platform):** `domain/actions/` (execution
  commands — enqueue/approve/cancel/resume), `domain/task_definition/`, `domain/sequences/` (platform
  content), and all infra adapters + entrypoints + jobs + loader.

### Deferred (couplings to route through ports — neither is exercised by step-node graphs)
- **Handler-node dispatch** (`node_factory._resolve_handler`) reaches the platform's service-layer
  registries → becomes a **dispatch port** in a later slice.
- **Content-node LLM call** (`compiler/nodes/content_node.py`) calls the Anthropic SDK directly →
  routes through the injected **`LLMPort`** in a later slice. The engine declares **no LLM-SDK
  dependency**; the `anthropic` import is deferred to call-time so the engine imports + compiles
  without it.

### Dependencies
- `langgraph`, `pydantic`, `networkx` (DAG validation), `pyyaml` (spec parsing), `prometheus-client`
  (compiler metrics). Deliberately **no LLM SDK** (that's the `LLMPort`'s job).

## [0.0.0] — 2026-06-16

## [0.0.0] — 2026-06-16
- Initial scaffold: package skeleton (`sulis_workflows`), CI, release pipeline, README.
  The engine extraction from the platform (`apps/api/sulis/shared/workflows`) follows;
  `v0.1.0` will land the pure core (domain + ports + compiler).
