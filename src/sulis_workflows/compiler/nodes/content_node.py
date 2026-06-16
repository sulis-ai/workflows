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

    Args:
        state_input_key: state field holding the compiled prompt.
        state_output_key: state field to write the LLM response into.
        llm: the injected `LLMPort` adapter (the engine never constructs an SDK client).
        model / max_tokens: request shaping, mapped by the adapter to its SDK.
        platform_id / run_id / timeout_s: tenancy + bound, threaded to every port call.

    Returns:
        An async callable suitable for a LangGraph function node.
    """

    async def content_fn(state: dict) -> dict:
        prompt = state.get(state_input_key, "")
        if not prompt:
            raise ValueError(
                f"Content node: state['{state_input_key}'] is empty — no prompt to send to the LLM"
            )
        response = await llm.complete(
            LLMRequest(prompt=prompt, model=model, max_tokens=max_tokens),
            platform_id=platform_id,
            run_id=run_id,
            timeout_s=timeout_s,
        )
        logger.info(
            "Content node produced %d chars from '%s' -> '%s'",
            len(response.text),
            state_input_key,
            state_output_key,
        )
        return {state_output_key: response.text}

    content_fn.__name__ = f"content_{state_input_key}_to_{state_output_key}"
    return content_fn
