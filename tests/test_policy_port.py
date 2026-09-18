"""PolicyPort — the seam ADR-022 found missing: nothing runs, dispatches or decides
without an authorization call through the policy port (spec §10.1, CLAUDE.md).

Mirrors the shape every other port in domain/ports/ already uses (LLMPort,
ToolDispatchPort, CheckpointingPort): a runtime_checkable Protocol, an
IdentifiedAdapter, tenancy keys (platform_id/run_id) on every call, and an
in-memory stub for contract tests.
"""

from __future__ import annotations

import asyncio

from sulis_workflows.domain.ports.policy import (
    PolicyDecision,
    PolicyPort,
    StubPolicyAdapter,
    Verdict,
)


def test_stub_adapter_satisfies_the_port():
    assert isinstance(StubPolicyAdapter(), PolicyPort)


def test_default_stub_permits():
    policy = StubPolicyAdapter()
    decision = asyncio.run(
        policy.authorize(
            "agents.recommendation.approve",
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    assert decision == PolicyDecision(verdict=Verdict.PERMIT)


def test_stub_can_be_seeded_to_deny_a_specific_permission():
    policy = StubPolicyAdapter(denies={"agents.recommendation.approve"})
    decision = asyncio.run(
        policy.authorize(
            "agents.recommendation.approve",
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    assert decision.verdict == Verdict.DENY


def test_stub_can_be_seeded_indeterminate():
    policy = StubPolicyAdapter(indeterminate={"agents.recommendation.approve"})
    decision = asyncio.run(
        policy.authorize(
            "agents.recommendation.approve",
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    assert decision.verdict == Verdict.INDETERMINATE


def test_denial_carries_a_rationale():
    policy = StubPolicyAdapter(denies={"agents.recommendation.approve"})
    decision = asyncio.run(
        policy.authorize(
            "agents.recommendation.approve",
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    assert decision.rationale


def test_tenancy_propagated_to_the_adapter():
    policy = StubPolicyAdapter()
    asyncio.run(
        policy.authorize(
            "agents.recommendation.approve",
            identity="user:iain",
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    assert policy.observed_calls == [("tenant-1", "run-1")]


def test_verdict_is_the_adr_028_vocabulary_exactly():
    # ADR-028: PERMIT | DENY | INDETERMINATE — no fourth value, no boolean stand-in.
    assert {v.value for v in Verdict} == {"PERMIT", "DENY", "INDETERMINATE"}
