# Adopting the engine in an existing codebase

How a **consumer becomes a runner** — replacing an in-app copy of the engine (or starting
fresh) with the published `sulis-workflows` package, and wiring its adapters. This is the
path for the **platform** (the server runner, which has an in-app copy at
`apps/api/sulis/shared/workflows`) and for any other consumer (the brain-runtime, agents).

> This page covers adopting the `compiler/` path (a `Workflow` entity → a LangGraph graph). The
> newer `definition/` + `engine/` path (the v1 process-definition format) has no equivalent
> adoption guide yet — see `docs/spec/process-definition.md` and `docs/work-packages/`.

## 1. Depend on the published package

```toml
# pyproject.toml
dependencies = ["sulis-workflows @ git+https://github.com/sulis-ai/workflows.git@v0.12.1"]
```

Pin a tag. Server and client runners pin the **same** version — that's what "one engine"
means in practice.

## 2. Replace the in-app engine with the package

Two paths (pick per how coupled the in-app copy is):

- **Shim (lowest-risk, recommended first):** keep the in-app module paths but re-export from
  the package, so the consumer's existing imports don't all change at once:
  ```python
  # apps/.../shared/workflows/compiler/__init__.py
  from sulis_workflows.compiler import *          # noqa: F401,F403
  from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler  # noqa: F401
  ```
  Then delete the in-app *implementation* files that moved (compiler + core domain), keeping
  the control-plane code (actions, service_layer, entrypoints, jobs, loader) + the app adapters.
- **Rewrite (clean end-state):** change the consumer's imports
  `…shared.workflows.{compiler,domain}` → `sulis_workflows.{compiler,domain}` and delete the
  in-app copies outright.

**What stays in the consumer (never moves to the engine):** the app adapters (Firestore,
GitHub, Cloud Run, …), entrypoints (HTTP routers), the control-plane/service-layer, jobs,
loader. The audit seam (DR-040): engine = `compiler/` + core `domain/`; everything else stays.

## 3. Wire your adapters via the `Adapters` bundle

The in-app composition root builds the adapters; pass them to the engine as one bundle:

```python
from sulis_workflows.runtime import Adapters
adapters = Adapters(
    llm=MyLLMAdapter(),                 # the app's real LLM adapter
    content_storage=GitHubAdapter(),     # the app's storage adapter
    checkpointing=FirestoreCheckpointer(),
)
graph = OutcomeGraphCompiler(spec_repo, adapters=adapters).compile(outcome_id=…)
```

Each adapter already implements its port Protocol (`LLMPort`, `ContentStoragePort`, …). The
engine resolves them by name; a missing one raises `MissingAdapterError` (the port + the fix).

## 4. Verify in the consumer's CI

A production consumer **must** validate the swap through its **own** test suite + deploy
pipeline — the engine's tests prove the engine; only the consumer's CI proves the consumer
still behaves identically after the swap. Treat it as: shim → run the full suite green →
(optionally) rewrite imports → run green again → ship behind the normal deploy gate. This is
a no-behaviour-change refactor; the consumer's CI is the gate that confirms it.

## Notes per consumer

- **Platform (server runner):** has the in-app copy; use the shim path first, keep its GCP
  adapters + control-plane, validate via the platform's CI. (This refactor is a focused,
  CI-backed effort — not a blind edit.)
- **brain-runtime (client runner):** no in-app copy — it consumes the package directly via its
  `runner/` (see that repo). Standalone placement (no control plane).
