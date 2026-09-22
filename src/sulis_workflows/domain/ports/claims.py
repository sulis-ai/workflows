"""ClaimsPort — leases for MUTATION/SIDE_EFFECT steps (spec §12.3, WP-02).

"Before a MUTATION or SIDE_EFFECT step runs, the engine writes an
in-progress claim with a lease, under the same write-once guard. A running
step renews its lease. A second caller is told STEP_RUNNING. An expired
claim MAY be taken over, and the takeover is logged as 'may already have
run'. Lease length is a host setting."

This is the at-most-once guard for effectful steps: without it, a resumed
run (a fresh process calling next(run, scope) after a crash, per §12.1)
could dispatch a MUTATION step a second time while the first attempt was
merely slow, not dead. A claim answers "is someone already doing this?"
before the engine ever calls the Tool.

Shares its key shape with RecordsPort's AttemptKey — a claim and an attempt
record are keyed identically, "under the same write-once guard" per §12.3 —
so a claim and its eventual attempt record are trivially correlated.

Shape follows the established sibling ports: a runtime_checkable Protocol
extending IdentifiedAdapter, tenancy keys on every call, an in-memory stub.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity
from sulis_workflows.domain.ports.records import AttemptKey

__all__ = [
    "Claim",
    "ClaimResult",
    "ClaimStatus",
    "ClaimsPort",
    "StubClaimsAdapter",
]


class ClaimStatus(str, Enum):
    """The three outcomes §12.3 names for an acquire attempt."""

    GRANTED = "GRANTED"
    STEP_RUNNING = "STEP_RUNNING"
    TAKEN_OVER = "TAKEN_OVER"


@dataclass(frozen=True)
class Claim:
    """An in-progress claim on one (run, scope, node, attempt)."""

    key: AttemptKey
    claimed_by: str
    claimed_at: float
    expires_at: float


@dataclass(frozen=True)
class ClaimResult:
    """The answer to one acquire/renew call.

    ``note`` carries the takeover log line ("may already have run") the
    spec requires when an expired claim is taken over — present only for
    ``TAKEN_OVER``.
    """

    status: ClaimStatus
    claim: Claim
    note: str | None = None


@runtime_checkable
class ClaimsPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic claim/lease protocol (§12.3).

    ``acquire`` is called before a MUTATION/SIDE_EFFECT step dispatches.
    ``renew`` is called by a still-running step to extend its lease before
    it expires; a renewed claim keeps the same key and claimant.
    """

    async def acquire(
        self,
        key: AttemptKey,
        *,
        lease_seconds: float,
        claimed_by: str,
        platform_id: str,
        run_id: str,
    ) -> ClaimResult: ...

    async def renew(
        self,
        claim: Claim,
        *,
        lease_seconds: float,
        platform_id: str,
        run_id: str,
    ) -> ClaimResult: ...


@dataclass
class StubClaimsAdapter:
    """In-memory stub for unit-mode contract tests.

    Backed by a dict keyed by :class:`AttemptKey`. Expiry is real
    wall-clock time (``time.time()``), not simulated, so a negative
    ``lease_seconds`` genuinely produces an already-expired claim —
    the shape the takeover test exercises.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _store: dict[AttemptKey, Claim] = field(default_factory=dict)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubClaimsAdapter",
            port_name="ClaimsPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def acquire(
        self,
        key: AttemptKey,
        *,
        lease_seconds: float,
        claimed_by: str,
        platform_id: str,
        run_id: str,
    ) -> ClaimResult:
        self.observed_calls.append((platform_id, run_id))
        now = time.time()
        existing = self._store.get(key)

        if existing is not None and existing.expires_at > now:
            return ClaimResult(status=ClaimStatus.STEP_RUNNING, claim=existing)

        new_claim = Claim(
            key=key,
            claimed_by=claimed_by,
            claimed_at=now,
            expires_at=now + lease_seconds,
        )
        self._store[key] = new_claim

        if existing is not None:
            return ClaimResult(
                status=ClaimStatus.TAKEN_OVER,
                claim=new_claim,
                note=f"claim on {key!r} expired while held by {existing.claimed_by!r}; "
                f"taken over by {claimed_by!r} — may already have run",
            )
        return ClaimResult(status=ClaimStatus.GRANTED, claim=new_claim)

    async def renew(
        self,
        claim: Claim,
        *,
        lease_seconds: float,
        platform_id: str,
        run_id: str,
    ) -> ClaimResult:
        """D42 (WP-05 Part 2): before this fix, `renew` blindly overwrote
        `self._store[claim.key]` with whatever `claimed_by`/`claimed_at`
        the CALLER'S OWN `claim` argument carried, never once reading the
        store's own current entry — so a caller whose claim had already
        expired and been taken over by someone else (`acquire`'s own
        `TAKEN_OVER` path) could still "renew" it, silently re-granting a
        lease to a caller who had already lost the race, defeating §12.3's
        own at-most-once guarantee. `renew` now looks up the CURRENT
        stored claim for `claim.key` and only extends it when this caller
        genuinely still holds it (same `claimed_by`, not yet expired) —
        otherwise it fails the same `TAKEN_OVER` way `acquire` already
        does for an expired-and-reclaimed key, rather than inventing a
        fourth status. `claim.claimed_at`/`claim.expires_at` are the
        caller's own possibly-stale echo of what it last saw — never
        trusted here; the store's own entry is authoritative.
        """
        self.observed_calls.append((platform_id, run_id))
        now = time.time()
        existing = self._store.get(claim.key)
        if (
            existing is None
            or existing.claimed_by != claim.claimed_by
            or existing.expires_at <= now
        ):
            current = existing if existing is not None else claim
            return ClaimResult(
                status=ClaimStatus.TAKEN_OVER,
                claim=current,
                note=(
                    f"claim on {claim.key!r} is no longer held by "
                    f"{claim.claimed_by!r} (now {current.claimed_by!r}) — cannot "
                    "renew; may already have run"
                ),
            )
        renewed = Claim(
            key=claim.key,
            claimed_by=existing.claimed_by,
            claimed_at=existing.claimed_at,
            expires_at=now + lease_seconds,
        )
        self._store[claim.key] = renewed
        return ClaimResult(status=ClaimStatus.GRANTED, claim=renewed)
