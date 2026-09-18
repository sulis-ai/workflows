"""RecordsPort — durable, write-once attempt records (spec §12.2, WP-02).

"Every attempt of every node is one write-once record keyed by (run, scope,
node, attempt): inputs used, output, control results, verdict or error, who
or what performed it ... and start and end times. The engine numbers
attempts. Loop counters, retry counts and progress are derived from
records."

This is the durability that makes §12.1's stateless contract true rather
than aspirational: "Starting and resuming are the same call. Nothing is
held in memory between calls." A fresh process answering next(run, scope)
reconstructs everything it needs — including loop and retry counts — by
reading records for that run; it holds nothing of its own.

``performed_by`` carries the W3C PROV-O ``prov:wasAssociatedWith`` relation
the spec names (known, not re-read) as an opaque identity string
(e.g. ``AGENT:interrogate@1``, ``PERSON:user-42``) — this port does not
implement PROV-O itself, only the one relation the spec calls out.

Shape follows the established sibling ports: a runtime_checkable Protocol
extending IdentifiedAdapter, tenancy keys on every call, an in-memory stub.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "AttemptKey",
    "AttemptRecord",
    "DuplicateAttempt",
    "RecordsPort",
    "StubRecordsAdapter",
]


@dataclass(frozen=True)
class AttemptKey:
    """The write-once key: (run, scope, node, attempt) — spec §12.2."""

    run: str
    scope: str
    node: str
    attempt: int


@dataclass(frozen=True)
class AttemptRecord:
    """One durable record of one attempt at one node.

    ``verdict`` carries a GATE's PERMIT/DENY/INDETERMINATE or a STEP's
    error code — whichever the node type produced; a STEP that succeeded
    outright leaves it ``None`` and relies on ``output``/``control_results``.
    """

    key: AttemptKey
    inputs: dict[str, Any]
    output: dict[str, Any] | None
    control_results: list[dict[str, Any]]
    verdict: str | None
    performed_by: str
    started_at: str
    ended_at: str


class DuplicateAttempt(Exception):
    """Raised when a record already exists for this key — the write-once guard.

    Carries the offending key so callers can decide whether this is a
    genuine double-write bug or a resumed call replaying work already done.
    """

    def __init__(self, *, key: AttemptKey) -> None:
        self.key = key
        super().__init__(f"attempt already recorded: {key!r}")


@runtime_checkable
class RecordsPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic durable-record protocol (§12.2).

    ``record_attempt`` MUST refuse (raise :class:`DuplicateAttempt`) a
    second write to the same :class:`AttemptKey` — attempts are numbered
    by the engine precisely so each write is genuinely new.

    ``get_attempts`` returns every recorded attempt for a node, in
    attempt order, so a caller can derive counts (loop iterations, retries)
    without holding any state of its own between calls.
    """

    async def record_attempt(
        self,
        record: AttemptRecord,
        *,
        platform_id: str,
        run_id: str,
    ) -> None: ...

    async def get_attempts(
        self,
        run: str,
        scope: str,
        node: str,
        *,
        platform_id: str,
        run_id: str,
    ) -> list[AttemptRecord]: ...


@dataclass
class StubRecordsAdapter:
    """In-memory stub for unit-mode contract tests.

    Backed by a dict keyed by :class:`AttemptKey`, so the write-once
    guard is exercised for real rather than assumed.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _store: dict[AttemptKey, AttemptRecord] = field(default_factory=dict)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubRecordsAdapter",
            port_name="RecordsPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def record_attempt(
        self,
        record: AttemptRecord,
        *,
        platform_id: str,
        run_id: str,
    ) -> None:
        self.observed_calls.append((platform_id, run_id))
        if record.key in self._store:
            raise DuplicateAttempt(key=record.key)
        self._store[record.key] = record

    async def get_attempts(
        self,
        run: str,
        scope: str,
        node: str,
        *,
        platform_id: str,
        run_id: str,
    ) -> list[AttemptRecord]:
        self.observed_calls.append((platform_id, run_id))
        matches = [
            rec
            for key, rec in self._store.items()
            if key.run == run and key.scope == scope and key.node == node
        ]
        return sorted(matches, key=lambda r: r.key.attempt)
