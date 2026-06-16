"""EXAMPLE (consumer-side, NOT part of the engine) — a real `LLMPort` adapter.

This shows how a **consumer / runner** provides a real LLM to the engine: implement
`LLMPort` by mapping `LLMRequest` → the Anthropic SDK and the SDK response →
`LLMResponse`. It lives in the *consumer's* codebase (here, `examples/`), so the engine
library never imports `anthropic`. Inject it exactly like the `StubLLMAdapter`:

    from examples.anthropic_llm_adapter import AnthropicLLMAdapter
    node = make_content_node("prompt", "answer", llm=AnthropicLLMAdapter(),
                             platform_id=tenant, run_id=run)

The consumer adds `anthropic` to *its* dependencies; the engine's stay SDK-free.
(Illustrative — the exact SDK calls track the installed `anthropic` version.)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sulis_workflows.domain.identity import AdapterIdentity, IdentifiedAdapter  # noqa: F401
from sulis_workflows.domain.ports.base import stub_identity
from sulis_workflows.domain.ports.llm import LLMRequest, LLMResponse, LLMStreamChunk


@dataclass
class AnthropicLLMAdapter:
    """A real `LLMPort` adapter wrapping the Anthropic SDK. Satisfies the Protocol
    structurally (no inheritance needed); declares an `AdapterIdentity` (ADR-209)."""

    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        # A real adapter builds a proper identity at the composition root; the stub
        # identity helper keeps this example self-contained.
        self._identity = stub_identity(adapter_class="AnthropicLLMAdapter", port_name="LLMPort")

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def complete(
        self, req: LLMRequest, *, platform_id: str, run_id: str, timeout_s: float
    ) -> LLMResponse:
        import anthropic  # the CONSUMER's dependency, not the engine's

        client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model=req.model,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            messages=[{"role": "user", "content": req.prompt}],
        )
        block = resp.content[0]
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=getattr(block, "text", ""),
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
        )

    async def stream(
        self, req: LLMRequest, *, platform_id: str, run_id: str, timeout_s: float
    ) -> AsyncIterator[LLMStreamChunk]:
        import anthropic

        client = anthropic.AsyncAnthropic()
        async with client.messages.stream(
            model=req.model,
            max_tokens=req.max_tokens,
            messages=[{"role": "user", "content": req.prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield LLMStreamChunk(delta=text, done=False)
        yield LLMStreamChunk(delta="", done=True)
