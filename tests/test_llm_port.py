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
from sulis_workflows.domain.ports.llm import LLMPort, LLMRequest, StubLLMAdapter


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


def test_content_node_passes_system_prompt_through_to_the_port():
    llm = StubLLMAdapter()
    node = make_content_node(
        "answer", "prompt", "reply", llm=llm, system_prompt="You are a strict classifier.",
    )
    out = asyncio.run(node({"step_outputs": {"prompt": "hello world"}}))
    assert out["step_outputs"] == {
        "reply": "stub-response:[system:You are a strict classifier.] hello world"
    }


def test_content_node_without_system_prompt_is_unaffected():
    llm = StubLLMAdapter()
    node = make_content_node("answer", "prompt", "reply", llm=llm)
    out = asyncio.run(node({"step_outputs": {"prompt": "hello world"}}))
    assert out["step_outputs"] == {"reply": "stub-response:hello world"}


def test_content_node_empty_system_prompt_string_is_treated_as_absent():
    llm = StubLLMAdapter()
    node = make_content_node("answer", "prompt", "reply", llm=llm, system_prompt="")
    out = asyncio.run(node({"step_outputs": {"prompt": "hi"}}))
    assert out["step_outputs"] == {"reply": "stub-response:hi"}


def test_llm_request_system_prompt_defaults_to_none():
    req = LLMRequest(prompt="hi", model="claude-sonnet-4-20250514")
    assert req.system_prompt is None


def test_llm_request_system_prompt_is_settable():
    req = LLMRequest(prompt="hi", model="claude-sonnet-4-20250514", system_prompt="be terse")
    assert req.system_prompt == "be terse"
