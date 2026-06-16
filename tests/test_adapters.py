"""Compile-level port injection — the seam a runner uses.

A runner injects the whole `Adapters` bundle once at `compile()`; the engine threads it
to every node that needs a port. Here: a `content` node resolves its `LLMPort` from the
bundle. Absent → a clear `MissingAdapterError`, never a crash.
"""

from __future__ import annotations

import asyncio

import pytest
from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.ports.llm import StubLLMAdapter
from sulis_workflows.domain.ports.tool_dispatch import StubToolDispatchAdapter
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


def test_content_workflow_runs_to_completion():
    # The real job: compile + RUN an LLM workflow to completion (not just compile).
    llm = StubLLMAdapter()
    graph = _compiler(Adapters(llm=llm)).compile(outcome_id="chat")
    initial = {
        "execution_id": "run-42", "outcome_id": "chat", "phase": "start",
        "completed_nodes": [], "step_outputs": {"prompt": "hello"},
        "gate_decisions": {}, "metadata": {"platform_id": "tenant-x"},
    }
    result = asyncio.run(graph.ainvoke(initial))
    assert result["step_outputs"].get("reply") == "stub-response:hello"  # real LLM-via-port output
    assert "answer" in result["completed_nodes"]
    # Tenancy (NFR-11/21): the live execution's identity reached the port.
    assert llm.observed_calls == [("tenant-x", "run-42")]


# --- step → ToolDispatchPort (real step work) ------------------------------------

_STEP_DAG = {"scan": {"dag": {"nodes": [
    {"id": "find", "type": "step", "spec_ref": "scan/find"},
]}}}
_STEP_SPECS = {"scan/find": {"primitive": "glob", "args": {"pattern": "*.py"}}}

_STEP_INITIAL = {
    "execution_id": "run-7", "outcome_id": "scan", "phase": "start",
    "completed_nodes": [], "step_outputs": {}, "gate_decisions": {},
    "metadata": {"platform_id": "tenant-a"},
}


def test_step_dispatches_a_tool_primitive_via_the_port():
    # The real job: a step node DISPATCHES its primitive through the injected
    # ToolDispatchPort and the result lands in step_outputs (not just a marker).
    stub = StubToolDispatchAdapter()
    compiler = OutcomeGraphCompiler(
        MemorySpecRepository(dags=_STEP_DAG, steps=_STEP_SPECS, sequences={}),
        adapters=Adapters(tool_dispatch=stub, sandbox_root="/work"),
    )
    graph = compiler.compile(outcome_id="scan")
    result = asyncio.run(graph.ainvoke(_STEP_INITIAL))

    out = result["step_outputs"]["find"]
    assert out["primitive"] == "glob"
    assert out["paths"] == ["stub-glob:*.py"]  # the port was really driven
    assert "find" in result["completed_nodes"]
    # Tenancy (NFR-11/21): the live execution's identity reached the adapter.
    assert stub.observed_calls == [("tenant-a", "run-7")]


def test_step_without_a_primitive_falls_back_to_recording_the_spec():
    # A non-tool step (no `primitive`) still compiles + runs — backward compat.
    specs = {"scan/find": {"description": "a plain step, no tool"}}
    compiler = OutcomeGraphCompiler(
        MemorySpecRepository(dags=_STEP_DAG, steps=specs, sequences={}),
    )
    graph = compiler.compile(outcome_id="scan")
    result = asyncio.run(graph.ainvoke(_STEP_INITIAL))

    out = result["step_outputs"]["find"]
    assert out["spec"] == {"description": "a plain step, no tool"}
    assert "find" in result["completed_nodes"]


def test_step_with_primitive_but_no_tool_dispatch_raises_a_clear_error():
    # A primitive step with no injected port fails loud (at execution), never silently.
    compiler = OutcomeGraphCompiler(
        MemorySpecRepository(dags=_STEP_DAG, steps=_STEP_SPECS, sequences={}),
    )  # no tool_dispatch injected
    graph = compiler.compile(outcome_id="scan")
    with pytest.raises(MissingAdapterError) as exc:
        asyncio.run(graph.ainvoke(_STEP_INITIAL))
    assert "tool_dispatch" in str(exc.value)
