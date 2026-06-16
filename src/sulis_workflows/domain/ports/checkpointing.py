"""CheckpointingPort — workflow-domain abstraction over LangGraph
checkpoint persistence (WP-MIG-6).

The existing SQLite checkpointer is the first concrete adapter behind
this port. The :class:`StubCheckpointingAdapter` in this module is
the in-memory double for unit-mode contract tests.

Per TDD §3.3 every method carries ``platform_id`` and ``run_id`` as
non-optional keyword arguments.

ADR-206 / WP-ARMOR-02 sign the payload externally — the port carries
the bytes opaquely. Adapters MUST NOT inspect or mutate the payload
body; round-trip integrity is the contract.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "CheckpointHandle",
    "CheckpointingPort",
    "CheckpointPayload",
    "StubCheckpointingAdapter",
    "UnknownCheckpoint",
]


@dataclass(frozen=True)
class CheckpointPayload:
    """The opaque checkpoint body.

    ``thread_id`` is the LangGraph thread identifier (carried through
    to the SQLite ``checkpoints`` table). ``body`` is the serialised
    state — adapters store and retrieve it verbatim.
    """

    thread_id: str
    body: bytes


@dataclass(frozen=True)
class CheckpointHandle:
    """Opaque handle returned from ``save``.

    Carries the adapter-specific identifier (SQLite row id, stub UUID).
    Callers MUST treat the field as opaque — only equality matters.
    """

    checkpoint_id: str


class UnknownCheckpoint(Exception):
    """Raised by ``load`` when the handle is not known to the adapter.

    Carries the offending ``checkpoint_id`` so error consumers can
    correlate. A handle the adapter never emitted, or one whose
    backing row has been deleted, both surface as this exception.
    """

    def __init__(self, *, checkpoint_id: str) -> None:
        self.checkpoint_id = checkpoint_id
        super().__init__(f"unknown checkpoint: {checkpoint_id!r}")


@runtime_checkable
class CheckpointingPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic checkpoint-persistence protocol.

    Two call shapes:

    - ``save`` — persist a payload; return a stable :class:`CheckpointHandle`.
    - ``load`` — round-trip the payload byte-identically for a handle
      the adapter has previously emitted; raise
      :class:`UnknownCheckpoint` for an unrecognised handle.

    Per TDD §3.3 every method carries the tenancy keys.
    """

    async def save(
        self,
        payload: CheckpointPayload,
        *,
        platform_id: str,
        run_id: str,
    ) -> CheckpointHandle: ...

    async def load(
        self,
        handle: CheckpointHandle,
        *,
        platform_id: str,
        run_id: str,
    ) -> CheckpointPayload: ...


@dataclass
class StubCheckpointingAdapter:
    """In-memory stub for unit-mode contract tests.

    Backed by a dict keyed by the emitted handle. ``save`` returns a
    fresh UUID-based handle; ``load`` returns the byte-identical
    payload or raises :class:`UnknownCheckpoint`.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _store: dict[str, CheckpointPayload] = field(default_factory=dict)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubCheckpointingAdapter",
            port_name="CheckpointingPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def save(
        self,
        payload: CheckpointPayload,
        *,
        platform_id: str,
        run_id: str,
    ) -> CheckpointHandle:
        self.observed_calls.append((platform_id, run_id))
        cid = f"stub-cp-{uuid.uuid4().hex[:8]}"
        self._store[cid] = payload
        return CheckpointHandle(checkpoint_id=cid)

    async def load(
        self,
        handle: CheckpointHandle,
        *,
        platform_id: str,
        run_id: str,
    ) -> CheckpointPayload:
        self.observed_calls.append((platform_id, run_id))
        try:
            return self._store[handle.checkpoint_id]
        except KeyError as exc:
            raise UnknownCheckpoint(checkpoint_id=handle.checkpoint_id) from exc
