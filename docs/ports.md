# Ports — how the engine takes its dependencies

The engine is **dependency-free of infrastructure**. Anything it needs from the outside
world — an LLM, content storage, checkpointing, observability, tool dispatch — it takes
through a **port**: a `Protocol` the engine defines and a **consumer/runner provides an
adapter for**. This is what lets the *same* engine run server-side or client-side
(DR-040): only the injected adapters differ.

> The engine declares **no** infrastructure SDKs (no `anthropic`, no DB driver). An
> adapter that imports an SDK lives in the **consumer**, never in this library.

## The shape: define → adapt → inject → invoke

Worked with the **`LLMPort`** (`domain/ports/llm.py`):

**1. Define** — the engine owns the Protocol + its value objects (no SDK types leak):

```python
@runtime_checkable
class LLMPort(IdentifiedAdapter, Protocol):
    async def complete(self, req: LLMRequest, *, platform_id: str, run_id: str,
                       timeout_s: float) -> LLMResponse: ...
    def stream(self, req: LLMRequest, *, ...) -> AsyncIterator[LLMStreamChunk]: ...
```

**2. Adapt** — a consumer implements it. The engine ships `StubLLMAdapter` (tests); a real
one wraps an SDK (see `examples/anthropic_llm_adapter.py`, which lives consumer-side):

```python
class AnthropicLLMAdapter:           # in the CONSUMER's code; imports `anthropic` there
    async def complete(self, req, *, platform_id, run_id, timeout_s) -> LLMResponse: ...
```

**3. Inject** — the runner hands the adapter to the engine where it's used:

```python
node = make_content_node("prompt", "answer", llm=AnthropicLLMAdapter(),
                         platform_id=tenant, run_id=run)
```

**4. Invoke** — the engine calls the *port*, not the SDK:

```python
resp = await llm.complete(LLMRequest(prompt=prompt, model=model), ...)
```

`tests/test_llm_port.py` proves this end-to-end with the stub (no SDK, no network).

## The ports (`domain/ports/`)

`LLMPort` · `ContentStoragePort` · `ToolDispatchPort` · `CheckpointingPort` ·
`ObservabilityPort` · `ExecutionRuntimePort` (+ execution-queue / repository / scheduler /
worker-pool). Each ships a `Stub*Adapter` so the engine is testable with no infrastructure.
Adapters extend `IdentifiedAdapter` (they declare an `AdapterIdentity`).

The newer `definition/` + `engine/` path (the v1 process-definition format) has its own three
ports, following the same shape, used by `engine/run.py`'s `next()`/`report()`/`decide()`/
`skip()`:

- **`PolicyPort`** (`domain/ports/policy.py`) — asks whether an identity holds a named
  permission; returns `PERMIT | DENY | INDETERMINATE` (sulis-ai/platform ADR-028).
- **`RecordsPort`** (`domain/ports/records.py`) — write-once attempt records keyed by
  `(run, scope, node, attempt)`; this is what makes `next()` genuinely stateless.
- **`ClaimsPort`** (`domain/ports/claims.py`) — leases for `MUTATION`/`SIDE_EFFECT` steps, so a
  resumed run cannot dispatch an already-in-progress effectful step twice.
- **`CodeToolPort`** (`domain/ports/code_tool.py`) — dispatches a `CODE`-mechanism Tool (§4.3)
  by its `ref`; distinct from the older `ToolDispatchPort` above, which the `compiler/` path uses.

Each ships a `Stub*Adapter` too. See `docs/spec/process-definition.md` §10–§12 for the
semantics they exist to satisfy.

## Injection seam — the `Adapters` bundle (one injection point)

A runner injects **all** its port adapters once, as an `Adapters` bundle, at `compile()`;
the engine threads them to every node that needs a port. This is the generic seam — one
object, every port, uniform resolution (a new port adds a field):

```python
from sulis_workflows.runtime import Adapters
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler

adapters = Adapters(llm=my_llm, content_storage=my_store, checkpointing=my_ckpt)  # what your placement needs
graph = OutcomeGraphCompiler(spec_repo, adapters=adapters).compile(outcome_id="…")
```

A node resolves its port from the bundle (e.g. a `content` node → `adapters.require("llm")`).
If a workflow needs a port the runner didn't inject, the engine raises a clear
**`MissingAdapterError`** naming the port + the fix — never a crash, never a fake.

- **Node factories** still accept a port directly (`make_content_node(..., llm=…)`) for
  fine-grained use/tests; the `Adapters` bundle is the runner-facing seam over them.
- **Tracing** is a port too: the engine defaults to a no-op `span_context` (`_tracing.py`);
  a consumer routes real spans via the `ObservabilityPort`.

## Why this matters (DR-040)

Ports are what make "one engine, many runners" real: a server runner injects Firestore /
GitHub / a real LLM; a client runner injects a local store / claude / stubs. The engine
code is identical; placement + adapters are the only difference.
