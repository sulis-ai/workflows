# Changelog

All notable changes to `sulis-workflows`. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: [SemVer](https://semver.org/). A release is a `vX.Y.Z` git tag.

## [Unreleased]

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
