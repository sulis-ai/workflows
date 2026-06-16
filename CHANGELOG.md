# Changelog

All notable changes to `sulis-workflows`. Format: [Keep a Changelog](https://keepachangelog.com/);
versioning: [SemVer](https://semver.org/). A release is a `vX.Y.Z` git tag.

## [Unreleased]

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

### Deferred
- **Handler-node dispatch** (`node_factory._resolve_handler`) still reaches the platform's
  service-layer registries; it is **not** exercised by step-node graphs. It becomes a **dispatch port**
  in a later slice. (Step-node compilation — the v0.1.0 surface — has no such coupling.)

## [0.0.0] — 2026-06-16

## [0.0.0] — 2026-06-16
- Initial scaffold: package skeleton (`sulis_workflows`), CI, release pipeline, README.
  The engine extraction from the platform (`apps/api/sulis/shared/workflows`) follows;
  `v0.1.0` will land the pure core (domain + ports + compiler).
