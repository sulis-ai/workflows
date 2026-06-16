"""Audit sink for adapter-identity mismatch events (ADR-209).

The engine guard (:func:`verify_adapter_identity`) emits an
:class:`IdentityMismatchEvent` to an :class:`IdentityAuditSink` whenever
an adapter call's reported identity differs from the active invocation
context's bindings.

This module declares the abstraction and ships an in-memory sink for
testing and composition-root local use. The production sink (PubSub-backed
observability) lives behind the observability port and is wired in by
WP-8 (instrumentation/run-id).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sulis_workflows.domain.identity import AdapterIdentity

__all__ = [
    "IdentityAuditSink",
    "IdentityMismatchEvent",
    "InMemoryIdentityAuditSink",
]


@dataclass(frozen=True)
class IdentityMismatchEvent:
    """Audit record emitted when adapter identity verification fails.

    Carries the (expected, observed) pair so operators can correlate the
    mismatch with the composition-root binding and the offending adapter.

    The expected field is None when no binding exists for ``port_name`` —
    distinguishing the 'wrong adapter on a bound port' case from the
    'unbound port reached an adapter call' case.

    Fields are deliberately primitive / dataclass-valued for downstream
    serialisation by the observability adapter.
    """

    port_name: str
    expected: AdapterIdentity | None
    observed: AdapterIdentity
    platform_id: str
    run_id: str


class IdentityAuditSink(Protocol):
    """Sink contract: emit an :class:`IdentityMismatchEvent`.

    Implementations MUST be fire-and-forget at the boundary — they MUST NOT
    raise on emit failure, because the guard is already raising the typed
    error. Buffering / batching / drop policies are implementation choices.
    """

    def emit(self, event: IdentityMismatchEvent) -> None: ...


class InMemoryIdentityAuditSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production sinks publish to the
    observability port instead.
    """

    def __init__(self) -> None:
        self._events: list[IdentityMismatchEvent] = []

    def emit(self, event: IdentityMismatchEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[IdentityMismatchEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)
