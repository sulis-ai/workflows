"""Compile-level port injection — the seam a runner uses.

A runner injects the whole `Adapters` bundle once at `compile()`; the engine threads it
to every node that needs a port. Here: a `content` node resolves its `LLMPort` from the
bundle. Absent → a clear `MissingAdapterError`, never a crash.
"""

from __future__ import annotations

import pytest
from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.ports.llm import StubLLMAdapter
from sulis_workflows.runtime import Adapters, MissingAdapterError

_CONTENT_DAG = {
    "chat": {"dag": {"nodes": [
        {"id": "answer", "type": "content", "config": {"input_key": "prompt", "output_key": "reply"}},
    ]}}
}


def _compiler(adapters: Adapters | None = None) -> OutcomeGraphCompiler:
    return OutcomeGraphCompiler(MemorySpecRepository(dags=_CONTENT_DAG, sequences={}), adapters=adapters)


def test_injected_llm_threads_through_compile_to_the_content_node():
    graph = _compiler(Adapters(llm=StubLLMAdapter())).compile(outcome_id="chat")
    assert isinstance(graph, CompiledStateGraph)


def test_missing_llm_adapter_raises_a_clear_error():
    with pytest.raises(MissingAdapterError) as exc:
        _compiler().compile(outcome_id="chat")  # no LLM injected
    assert "llm" in str(exc.value)
