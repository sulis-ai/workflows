"""Content node — wraps Anthropic messages.create() for LLM-powered graph nodes.

Separates content generation (LLM, judgment-based) from process execution
(deterministic, graph-managed). Content nodes read a compiled prompt from state,
call the Anthropic API, and write the response back to state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

# NOTE (DR-040 / engine purity): a content node should call the LLM via the injected
# `LLMPort`, not import the Anthropic SDK directly. Until that port wiring lands, the
# `anthropic` import is deferred to call-time (below) so the engine imports + compiles
# with no LLM-SDK dependency. Executing a content node still needs `anthropic` installed;
# routing it through `LLMPort` is a follow-on slice (same shape as the handler-node port).

logger = logging.getLogger(__name__)


def make_content_node(
    state_input_key: str,
    state_output_key: str,
    *,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
) -> Callable:
    """Create an async content node that calls the Anthropic API.

    Args:
        state_input_key: State field containing the compiled prompt.
        state_output_key: State field to write LLM response into.
        model: Anthropic model ID.
        max_tokens: Maximum tokens in response.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def content_fn(state: dict) -> dict:
        prompt = state.get(state_input_key, "")
        if not prompt:
            raise ValueError(
                f"Content node: state['{state_input_key}'] is empty — no prompt to send to LLM"
            )

        import anthropic  # deferred — see module note (belongs behind LLMPort)

        client = anthropic.AsyncAnthropic()
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        first_block = response.content[0]
        if not hasattr(first_block, "text"):
            raise ValueError(f"Content node: expected TextBlock, got {type(first_block).__name__}")
        text: str = first_block.text

        logger.info(
            "Content node produced %d chars from '%s' -> '%s'",
            len(text),
            state_input_key,
            state_output_key,
        )
        return {state_output_key: text}

    content_fn.__name__ = f"content_{state_input_key}_to_{state_output_key}"
    return content_fn
