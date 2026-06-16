# sulis-workflows

The **Sulis workflow engine** — a shared, published library. It compiles canonical
`Workflow` entities into a [LangGraph](https://langchain-ai.github.io/langgraph/)
graph and executes it under **injected adapters**, so the *same* engine runs
server-side or client-side. Per **DR-040** (the workflow-engine boundary).

## The model: one engine, one control plane, N runners

There is **one engine** (this library) — never a separate client-engine. What differs
per placement is the **runner** (host + injected adapters), not the engine:

- **Engine library** (this repo) — the compiler (`Workflow` entities → LangGraph graph)
  + graph execution + the **ports**. Embedded in every runner.
- **Control plane** (server-side, *not* in this repo) — run registry, dispatch, durable
  state, run/resume/status, human-in-the-loop routing. Orchestrates; never executes
  business logic.
- **Runners** — each = this library + adapters + (optionally) a control-plane connection.
  A *server runner* (cloud worker: Firestore/GitHub adapters) and a *client runner*
  (a local CLI / MCP server: store-backed + local adapters) run the **same library**,
  differing only in adapters + placement.

**Two execution modes:** *connected* (a control plane dispatches a run to a runner) and
*standalone* (a client runner runs the library in-process, no control plane).

## Layout

```
src/sulis_workflows/
  domain/          # pure domain: models, errors, identity, signing
  domain/ports/    # the Protocol ports adapters implement (LLM, ContentStorage,
                   # ToolDispatch, Checkpointing, Observability, ExecutionRuntime)
  compiler/        # canonical Workflow entities → LangGraph StateGraph
  runtime/         # the runner-facing surface: the Adapters bundle (inject ports)
```

Adapters (Firestore, GitHub, Cloud Run, a local store, claude) live in the **consumers**,
injected at the ports — never in this library.

## Getting started

See **[docs/getting-started.md](docs/getting-started.md)** for a compile-and-run walkthrough,
**[docs/ports.md](docs/ports.md)** for how the engine takes its dependencies (the ports), and
**[docs/adopting.md](docs/adopting.md)** for adopting the engine in an existing codebase
(replacing an in-app copy with the package + wiring adapters — the path for the platform/server runner).

## Install (consumers)

Pin a released tag:

```bash
pip install "git+https://github.com/sulis-ai/workflows.git@v0.3.0"
```

(PyPI publication is a later option; git-tag install is the zero-infra default.)

## Releases

Trunk-based: `main` is the release line; work lands via `feature/*` PRs. A release is a
**semver git tag** (`vMAJOR.MINOR.PATCH`); the release CI builds the package + cuts a
GitHub release. See `CHANGELOG.md`. Consumers depend on a tag, so the engine version is
explicit on both server and client runners.

## Status

**v0.3.0 — engine core + the generic port mechanism.** The core (`compiler/` + `domain/`)
is extracted from the platform and compiles a graph standalone (zero platform dependency).
A runner injects all its port adapters as one `Adapters` bundle at `compile()`; content
nodes call the LLM through the injected `LLMPort` (the engine carries no LLM-SDK dependency).
See `docs/getting-started.md`, `docs/ports.md`, and `CHANGELOG.md`.

Next: the platform consumes this package (server runner); the brain-runtime consumes it
(client runner); handler-node dispatch becomes a port; `compile()`-time adapters extend to
the remaining node types.
