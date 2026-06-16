"""Content node — an LLM-powered graph node, via the injected `LLMPort`.

A content node reads a compiled prompt from state, calls the LLM **through the
adapter-agnostic `LLMPort`** (never a specific SDK — the engine carries no LLM
dependency), and writes the response back to state. The consumer/runner injects the
adapter: a real one (e.g. an Anthropic or Claude-Code adapter — see
`examples/anthropic_llm_adapter.py`) or the `StubLLMAdapter` in tests. This is the
canonical "how the engine supports a port" shape (DR-040): the engine depends on the
Protocol; the consumer provides the implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sulis_workflows.domain.ports.llm import LLMPort, LLMRequest

logger = logging.getLogger(__name__)


def make_content_node(
    node_id: str,
    state_input_key: str,
    state_output_key: str,
    *,
    llm: LLMPort,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    platform_id: str = "",
    run_id: str = "",
    timeout_s: float = 60.0,
) -> Callable:
    """Create an async content node that calls the LLM via the injected `llm` port.

    I/O flows through the `step_outputs` channel of `OFMGraphState` (the engine's data-flow
    channel, which has a merge reducer) — reads the prompt from `step_outputs[input_key]`,
    writes the response to `step_outputs[output_key]`. (Top-level state keys are dropped by
    the typed schema; `step_outputs` is the right channel — same as step nodes use.)

    Args:
        node_id: this node's id (recorded in `completed_nodes`).
        state_input_key / state_output_key: keys within `step_outputs` to read/write.
        llm: the injected `LLMPort` adapter (the engine never constructs an SDK client).
        model / max_tokens: request shaping, mapped by the adapter to its SDK.
        platform_id / run_id / timeout_s: tenancy + bound, threaded to every port call.
    """

    async def content_fn(state: dict) -> dict:
        outputs = state.get("step_outputs") or {}
        prompt = outputs.get(state_input_key, "")
        if not prompt:
            raise ValueError(
                f"Content node '{node_id}': step_outputs['{state_input_key}'] is empty — "
                "no prompt to send to the LLM"
            )
        # Tenancy (NFR-11/21): the live execution's identity reaches the LLM port.
        # Factory args win if set; else derive from the running state.
        meta = state.get("metadata") or {}
        eff_platform_id = platform_id or str(meta.get("platform_id", ""))
        eff_run_id = run_id or str(state.get("execution_id", ""))
        response = await llm.complete(
            LLMRequest(prompt=prompt, model=model, max_tokens=max_tokens),
            platform_id=eff_platform_id,
            run_id=eff_run_id,
            timeout_s=timeout_s,
        )
        logger.info(
            "Content node '%s' produced %d chars ('%s' -> '%s')",
            node_id,
            len(response.text),
            state_input_key,
            state_output_key,
        )
        return {"step_outputs": {state_output_key: response.text}, "completed_nodes": [node_id]}

    content_fn.__name__ = f"content_{node_id}"
    return content_fn
