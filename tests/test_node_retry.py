"""Proves DAGNode.retry (parsed by dag_parser.py, dead since v0.1.0) is now actually wired
to LangGraph's native RetryPolicy — a content node whose LLMPort raises a transient failure
retries and completes; one that raises a permanent failure fails immediately, no retry.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.infrastructure.memory_spec_repo import MemorySpecRepository
from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.errors import PermanentPortError, TransientPortError
from sulis_workflows.domain.identity import AdapterIdentity
from sulis_workflows.domain.ports.base import stub_identity
from sulis_workflows.domain.ports.llm import LLMResponse
from sulis_workflows.runtime.adapters import Adapters

_DAG = {"flow": {"dag": {"nodes": [
    {"id": "answer", "type": "content", "config": {"input_key": "prompt", "output_key": "reply"}},
]}}}


@dataclass
class _FlakyLLM:
    """Raises TransientPortError `fail_times` times, then succeeds."""

    fail_times: int
    calls: int = 0
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(adapter_class="_FlakyLLM", port_name="LLMPort")

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def complete(self, req, *, platform_id, run_id, timeout_s):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TransientPortError(f"blip on call {self.calls}")
        return LLMResponse(text="recovered")


@dataclass
class _AlwaysPermanentLLM:
    calls: int = 0
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(adapter_class="_AlwaysPermanentLLM", port_name="LLMPort")

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def complete(self, req, *, platform_id, run_id, timeout_s):
        self.calls += 1
        raise PermanentPortError("malformed input, retrying won't help")


def _compile():
    spec_repo = MemorySpecRepository(dags=_DAG, sequences={})
    return spec_repo


def test_content_node_carries_a_default_retry_policy():
    compiler = OutcomeGraphCompiler(spec_repo=_compile(), adapters=Adapters(llm=_FlakyLLM(fail_times=0)))
    graph = compiler.compile(outcome_id="flow")
    assert isinstance(graph, CompiledStateGraph)
    node = graph.nodes["answer"]
    assert node.retry_policy is not None


def test_transient_failure_retries_and_the_run_completes():
    flaky = _FlakyLLM(fail_times=2)
    compiler = OutcomeGraphCompiler(spec_repo=_compile(), adapters=Adapters(llm=flaky))
    graph = compiler.compile(outcome_id="flow")
    result = asyncio.run(graph.ainvoke({"step_outputs": {"prompt": "hi"}}))
    assert result["step_outputs"]["reply"] == "recovered"
    assert flaky.calls == 3  # failed twice, succeeded on the third whole-node re-invocation


def test_permanent_failure_does_not_retry():
    perm = _AlwaysPermanentLLM()
    compiler = OutcomeGraphCompiler(spec_repo=_compile(), adapters=Adapters(llm=perm))
    graph = compiler.compile(outcome_id="flow")
    try:
        asyncio.run(graph.ainvoke({"step_outputs": {"prompt": "hi"}}))
        raised = False
    except PermanentPortError:
        raised = True
    assert raised
    assert perm.calls == 1  # no retry at all


def test_explicit_max_attempts_zero_opts_a_node_out():
    dag = {"flow": {"dag": {"nodes": [
        {"id": "answer", "type": "content", "config": {"input_key": "prompt", "output_key": "reply"},
         "retry": {"max_attempts": 0}},
    ]}}}
    spec_repo = MemorySpecRepository(dags=dag, sequences={})
    graph = OutcomeGraphCompiler(spec_repo=spec_repo, adapters=Adapters(llm=_FlakyLLM(fail_times=0))).compile(
        outcome_id="flow"
    )
    node = graph.nodes["answer"]
    assert node.retry_policy is None


def test_gate_nodes_get_no_default_retry_policy():
    dag = {"flow": {"dag": {"nodes": [{"id": "approve", "type": "gate", "config": {}}]}}}
    spec_repo = MemorySpecRepository(dags=dag, sequences={})
    graph = OutcomeGraphCompiler(spec_repo=spec_repo).compile(outcome_id="flow")
    node = graph.nodes["approve"]
    assert node.retry_policy is None
