"""The standalone proof: the engine compiles a canonical DAG into a LangGraph graph
with no platform dependency — using only the in-memory spec repo + langgraph.

Step-node compilation is the v0.1.0 surface. The handler-node path (`_resolve_handler`)
still reaches the platform's service-layer registries; that becomes a dispatch *port* in
a later slice (it is NOT exercised by step-node graphs).
"""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler

_DAG = {"smoke": {"dag": {"nodes": [{"id": "step-1", "type": "step", "spec_ref": "test/x"}]}}}


def test_compiles_a_step_graph_standalone():
    spec_repo = MemorySpecRepository(dags=_DAG, sequences={})
    graph = OutcomeGraphCompiler(spec_repo=spec_repo).compile(outcome_id="smoke")
    assert isinstance(graph, CompiledStateGraph)


def test_two_step_dag_compiles():
    dag = {"flow": {"dag": {"nodes": [
        {"id": "a", "type": "step", "spec_ref": "test/a"},
        {"id": "b", "type": "step", "spec_ref": "test/b"},
    ]}}}
    graph = OutcomeGraphCompiler(spec_repo=MemorySpecRepository(dags=dag, sequences={})).compile(outcome_id="flow")
    assert isinstance(graph, CompiledStateGraph)
