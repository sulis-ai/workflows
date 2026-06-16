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
```

Adapters (Firestore, GitHub, Cloud Run, a local store, claude) live in the **consumers**,
injected at the ports — never in this library.

## Install (consumers)

Pin a released tag:

```bash
pip install "git+https://github.com/sulis-ai/workflows.git@v0.1.0"
```

(PyPI publication is a later option; git-tag install is the zero-infra default.)

## Releases

Trunk-based: `main` is the release line; work lands via `feature/*` PRs. A release is a
**semver git tag** (`vMAJOR.MINOR.PATCH`); the release CI builds the package + cuts a
GitHub release. See `CHANGELOG.md`. Consumers depend on a tag, so the engine version is
explicit on both server and client runners.

## Status

Scaffold (v0.0.0). The engine is being extracted from the platform's
`apps/api/sulis/shared/workflows` (audited CLEAN-EXTRACT) into this shared library;
`v0.1.0` lands the pure core (domain + ports + compiler).
