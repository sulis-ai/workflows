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


def test_renew_after_someone_else_took_over_fails_cleanly_rather_than_re_granting():
    """D42 (WP-05 Part 2): the bad-but-conformant case `renew`'s own
    earlier, unconditional-overwrite implementation missed — a caller
    whose claim already expired and was taken over by someone else
    calling `acquire` again must not be able to "renew" its own,
    now-stale claim back into existence."""
    claims = StubClaimsAdapter()
    first = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=-1, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    takeover = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine-2", platform_id="t", run_id="r"
        )
    )
    assert takeover.status == ClaimStatus.TAKEN_OVER

    renew_attempt = asyncio.run(
        claims.renew(first.claim, lease_seconds=30, platform_id="t", run_id="r")
    )
    assert renew_attempt.status == ClaimStatus.TAKEN_OVER
    assert "may already have run" in renew_attempt.note
    # The genuine current holder's own claim is untouched by the stale renewal attempt.
    assert renew_attempt.claim.claimed_by == "engine-2"


def test_renew_of_an_already_expired_but_not_yet_taken_over_claim_fails_cleanly():
    """Even with no second claimant yet, a caller may not renew a lease
    that has already lapsed — §12.3's own time-bound guarantee, not a
    guarantee that holds only once someone else happens to show up."""
    claims = StubClaimsAdapter()
    first = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=-1, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    renew_attempt = asyncio.run(
        claims.renew(first.claim, lease_seconds=30, platform_id="t", run_id="r")
    )
    assert renew_attempt.status == ClaimStatus.TAKEN_OVER


def test_renew_before_expiry_extends_the_deadline_a_stale_takeover_attempt_then_fails():
    """A1 (WP-05 Part 2): renewing before expiry genuinely extends the
    deadline — a later `acquire` racing in still sees the RENEWED
    `expires_at`, not the original one, and is told `STEP_RUNNING` rather
    than being allowed to take over."""
    claims = StubClaimsAdapter()
    first = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    renewed = asyncio.run(
        claims.renew(first.claim, lease_seconds=30, platform_id="t", run_id="r")
    )
    assert renewed.status == ClaimStatus.GRANTED
    assert renewed.claim.expires_at > first.claim.expires_at

    still_running = asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine-2", platform_id="t", run_id="r"
        )
    )
    assert still_running.status == ClaimStatus.STEP_RUNNING


def test_tenancy_propagated_to_the_adapter():
    claims = StubClaimsAdapter()
    asyncio.run(
        claims.acquire(
            _key(), lease_seconds=30, claimed_by="engine", platform_id="t", run_id="r"
        )
    )
    assert claims.observed_calls == [("t", "r")]
