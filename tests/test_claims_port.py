"""ClaimsPort — leases for MUTATION/SIDE_EFFECT steps (spec §12.3).

Before a MUTATION or SIDE_EFFECT step runs, the engine writes an in-progress
claim with a lease, under the same write-once guard as records. A running
step renews its lease. A second caller is told the step is already running.
An expired claim MAY be taken over, and the takeover is logged as
"may already have run".
"""

from __future__ import annotations

import asyncio

from sulis_workflows.domain.ports.claims import (
    Claim,
    ClaimsPort,
    ClaimStatus,
    StubClaimsAdapter,
)
from sulis_workflows.domain.ports.records import AttemptKey


def _key() -> AttemptKey:
    return AttemptKey(run="run-1", scope="root", node="send-email", attempt=1)


def test_stub_adapter_satisfies_the_port():
    assert isinstance(StubClaimsAdapter(), ClaimsPort)


def test_first_claim_is_granted():
    claims = StubClaimsAdapter()
    result = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    assert result.status == ClaimStatus.GRANTED
    assert isinstance(result.claim, Claim)


def test_second_caller_while_unexpired_is_told_step_running():
    claims = StubClaimsAdapter()
    asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    result = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine-2", platform_id="t", run_id="r"
        )
    )
    assert result.status == ClaimStatus.STEP_RUNNING


def test_renew_extends_the_lease_of_the_same_claim():
    claims = StubClaimsAdapter()
    first = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    renewed = asyncio.run(
        claims.renew(first.claim, lease_seconds=30, platform_id="t", run_id="r")
    )
    assert renewed.claim.expires_at > first.claim.expires_at


def test_expired_claim_may_be_taken_over_and_the_takeover_is_logged():
    claims = StubClaimsAdapter()
    first = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=-1, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    assert (
        first.status == ClaimStatus.GRANTED
    )  # a lease of -1s is already expired by the time we check
    takeover = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine-2", platform_id="t", run_id="r"
        )
    )
    assert takeover.status == ClaimStatus.TAKEN_OVER
    assert "may already have run" in takeover.note


def test_tenancy_propagated_to_the_adapter():
    claims = StubClaimsAdapter()
    asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    assert claims.observed_calls == [("t", "r")]
