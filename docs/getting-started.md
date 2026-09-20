# Getting started

`sulis-workflows` is a **workflow engine library**: it compiles a workflow (a DAG of nodes)
into a [LangGraph](https://langchain-ai.github.io/langgraph/) graph and runs it. It owns no
infrastructure — you (the *runner*) inject the adapters it needs. The same library runs
server-side or on a client machine; only the adapters differ.

## Install

```bash
pip install "git+https://github.com/sulis-ai/workflows.git@v0.12.1"
```

> This page covers the `compiler/` path (a `Workflow` entity → a LangGraph graph). For the newer
> declarative process-definition format and its execution engine, see
> `docs/spec/process-definition.md` and `docs/work-packages/`.

## The four things you work with

| Concept | What it is | Where |
|---|---|---|
| **SpecRepository** | where workflow specs (DAGs) come from | `compiler/ports/spec_repository.py`; `MemorySpecRepository` for dev/tests |
| **Adapters** | the port implementations you inject (LLM, storage, checkpointing…) | `sulis_workflows.runtime.Adapters` — see [ports.md](ports.md) |
| **Compiler** | turns a DAG into a runnable LangGraph graph | `OutcomeGraphCompiler` |
| **The graph** | a standard compiled LangGraph you `ainvoke` | returned by `.compile()` |

## Compile + run a workflow

```python
import asyncio
from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.ports.llm import StubLLMAdapter
from sulis_workflows.runtime import Adapters

# 1. where the workflow comes from (here, in-memory; real runners use a file/brain-backed repo)
spec_repo = MemorySpecRepository(
    dags={"chat": {"dag": {"nodes": [
        {"id": "answer", "type": "content",
         "config": {"input_key": "prompt", "output_key": "reply"}},
    ]}}},
    sequences={},
)

# 2. inject the adapters your placement needs (StubLLMAdapter here; a real LLM in prod)
adapters = Adapters(llm=StubLLMAdapter())

# 3. compile -> a runnable LangGraph graph
graph = OutcomeGraphCompiler(spec_repo, adapters=adapters).compile(outcome_id="chat")

# 4. run it (LangGraph's async API). Node I/O flows through the `step_outputs` channel.
initial = {"execution_id": "e1", "outcome_id": "chat", "phase": "start",
           "completed_nodes": [], "step_outputs": {"prompt": "hello"},
           "gate_decisions": {}, "metadata": {}}
result = asyncio.run(graph.ainvoke(initial))
print(result["step_outputs"]["reply"])   # -> "stub-response:hello" (the stub echoes)
```

> Node data flows through `step_outputs` (a merge-reducer channel on the state) — a node reads
> its inputs from `step_outputs[...]` and writes its outputs back. Top-level state keys outside
> the schema are dropped, so use `step_outputs` (or `metadata`) for data flow.

Swap `StubLLMAdapter()` for a real `LLMPort` adapter (e.g.
[`examples/anthropic_llm_adapter.py`](../examples/anthropic_llm_adapter.py)) and the *same*
graph talks to a real model. That's the point: the engine code is identical; you change the
adapter.

## Node types

`step` (run a stage primitive) · `content` (call the LLM via `LLMPort`) · `gate` ·
`fan_out` / `routing` / `for_each` / `while` (control flow). A node that needs a port
resolves it from the injected `Adapters`; if it's absent you get a clear `MissingAdapterError`.

## Next

- **[ports.md](ports.md)** — how the engine takes its dependencies (the port pattern + the full port list).
- **CHANGELOG.md** — what shipped per version + the engine/control-plane boundary.
- The architecture rationale lives in the brain's decision record **DR-040** (the engine is a
  shared library; runners inject adapters; server- and client-side execution).
