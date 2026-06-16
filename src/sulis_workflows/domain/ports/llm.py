"""LLM port — adapter-agnostic large-language-model interface (WP-MIG-6).

Production adapters (Anthropic, Claude Code) implement this protocol;
they migrate from ``tasks/llm_backend.py`` behind this port in WP-MIG-2.
The :class:`StubLLMAdapter` here is the in-memory test double — it
ships green today so the contract test fixture
(``tests/contracts/llm_port_contract.py``) can run without any
credential-gated adapter present.

Per TDD §3.3:

- ``platform_id`` (NFR-21) and ``run_id`` (NFR-11) are required
  keyword-only arguments on every call site.
- Adapters MUST extend :class:`IdentifiedAdapter` (ADR-209) and
  declare their :class:`AdapterIdentity` at composition-root
  construction. The stub satisfies this minimally.

The port intentionally does NOT carry any LLM SDK type leaks — neither
``anthropic`` nor ``claude_code`` types appear here. Mapping happens
inside the adapter (per FR-14, lint L3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "LLMPort",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "StubLLMAdapter",
]


@dataclass(frozen=True)
class LLMRequest:
    """Adapter-agnostic LLM request value-object.

    Carries the prompt and the model selector. Adapters map this onto
    their SDK-specific request shape (system prompts, tool schemas,
    sampling params) at the adapter boundary.
    """

    prompt: str
    model: str
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass(frozen=True)
class LLMResponse:
    """Adapter-agnostic LLM completion result.

    Carries the generated text plus the input + output token counts.
    Token-count fields are advisory — adapters return what their SDK
    surfaces; consumers (the engine cache, observability) treat
    missing counts as zero.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMStreamChunk:
    """One token or token-group delta in a streamed completion."""

    delta: str
    done: bool = False


@runtime_checkable
class LLMPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic LLM protocol.

    Two call shapes:

    - ``complete`` for one-shot completions. Adapter awaits the full
      response and returns it.
    - ``stream`` for incremental delivery. Adapter yields
      :class:`LLMStreamChunk` instances; consumer iterates with
      ``async for``.

    Per TDD §3.3 every signature carries ``platform_id``, ``run_id``,
    and ``timeout_s``.
    """

    async def complete(
        self,
        req: LLMRequest,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> LLMResponse: ...

    def stream(
        self,
        req: LLMRequest,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> AsyncIterator[LLMStreamChunk]: ...


@dataclass
class StubLLMAdapter:
    """In-memory stub for unit-mode contract tests.

    Returns a deterministic echo response and yields a fixed three-
    chunk stream. Records every call's ``(platform_id, run_id)`` so
    the contract fixture can assert tenancy propagation without
    inspecting the adapter's internals beyond a public list.

    The identity is built once at construction; it satisfies
    :class:`IdentifiedAdapter` (ADR-209).
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubLLMAdapter",
            port_name="LLMPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def complete(
        self,
        req: LLMRequest,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> LLMResponse:
        self.observed_calls.append((platform_id, run_id))
        return LLMResponse(
            text=f"stub-response:{req.prompt}",
            input_tokens=len(req.prompt.split()),
            output_tokens=4,
        )

    async def stream(
        self,
        req: LLMRequest,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Yield a fixed three-chunk stream for the contract test.

        Implemented as an ``async def`` generator so the type checker
        sees the same protocol shape the production adapters will
        satisfy (Anthropic returns an async iterator over its own
        chunk type, which the adapter maps into :class:`LLMStreamChunk`).
        """
        self.observed_calls.append((platform_id, run_id))
        for delta in ("stub-", "response:", req.prompt):
            yield LLMStreamChunk(delta=delta, done=False)
        yield LLMStreamChunk(delta="", done=True)
