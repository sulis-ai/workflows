# Changelog

All notable changes to `sulis-workflows`. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: [SemVer](https://semver.org/). A release is a `vX.Y.Z` git tag.

## [Unreleased]

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
