"""How the engine supports a port — define → adapt → inject → invoke.

The engine defines `LLMPort` (a Protocol) and a content node that depends on it. A
consumer provides the adapter; here we use the in-engine `StubLLMAdapter` (no LLM SDK,
no network) — the *same shape* a real Anthropic / Claude-Code adapter satisfies
(see `examples/anthropic_llm_adapter.py`). This proves the engine carries no LLM
dependency and the adapter is genuinely swappable.
"""

from __future__ import annotations

import asyncio

import pytest

from sulis_workflows.compiler.nodes.content_node import make_content_node
from sulis_workflows.domain.ports.llm import LLMPort, StubLLMAdapter


def test_stub_adapter_satisfies_the_port():
    # runtime_checkable Protocol — the stub IS an LLMPort.
    assert isinstance(StubLLMAdapter(), LLMPort)


def test_content_node_uses_injected_llm_port():
    llm = StubLLMAdapter()                                       # adapt (consumer's adapter; stub here)
    node = make_content_node(                                    # inject the port into the node
        "answer", "prompt", "reply", llm=llm, platform_id="tenant-1", run_id="run-1"
    )
    # I/O flows through step_outputs (the engine's data channel)
    out = asyncio.run(node({"step_outputs": {"prompt": "hello world"}}))
    assert out["step_outputs"] == {"reply": "stub-response:hello world"}  # the stub echoes
    assert out["completed_nodes"] == ["answer"]
    # tenancy (platform_id / run_id) propagated through the port — not the SDK
    assert llm.observed_calls == [("tenant-1", "run-1")]


def test_content_node_requires_a_prompt():
    node = make_content_node("answer", "prompt", "reply", llm=StubLLMAdapter())
    with pytest.raises(ValueError):
        asyncio.run(node({"step_outputs": {}}))
