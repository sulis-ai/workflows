"""GATE execution — spec §7.6, WP-02 step 4.

Covers resolve_gate's sequencing, the policy decider (engine-run), and
check_agent_decision's evidence/separation-of-duty checks. The agent/person
hand-off machinery itself (asking, waiting) belongs to next()/report()
(step 5); here the caller always supplies precomputed decisions.
"""

from __future__ import annotations

import asyncio

from sulis_workflows.definition.model import Decider, GateNode, RouteTarget
from sulis_workflows.domain.ports.policy import StubPolicyAdapter, Verdict
from sulis_workflows.engine.gates import (
    DeciderOutcome,
    GateResolution,
    check_agent_decision,
    evaluate_policy_decider,
    resolve_gate,
)


def _gate(**overrides) -> GateNode:
    defaults = {
        "id": "sign-off",
        "kind": "APPROVAL",
        "asks": "Can these recommendations go ahead?",
        "reviewing": ("state.recommendations", "state.confidence"),
        "deciders": (
            Decider(kind="policy", ref="sign-off-policy@1"),
            Decider(kind="agent", ref="review-recommendations@1"),
            Decider(kind="person", permission="agents.recommendation.approve"),
        ),
        "on": {
            "PERMIT": RouteTarget(next="decompose-to-work"),
            "DENY": RouteTarget(next="recommend"),
        },
    }
    defaults.update(overrides)
    return GateNode(**defaults)


def _outcome(index: int, verdict: Verdict, decided_by: str) -> DeciderOutcome:
    return DeciderOutcome(decider_index=index, verdict=verdict, decided_by=decided_by)


def test_no_outcomes_yet_needs_the_first_decider_which_is_policy():
    decision = resolve_gate(_gate(), [], person_required=False)
    assert decision.resolution is GateResolution.NEEDS_POLICY
    assert decision.next_decider_index == 0


def test_a_permit_from_the_first_decider_decides_immediately():
    outcomes = [_outcome(0, Verdict.PERMIT, "POLICY:sign-off-policy@1")]
    decision = resolve_gate(_gate(), outcomes, person_required=False)
    assert decision.resolution is GateResolution.DECIDED
    assert decision.verdict is Verdict.PERMIT


def test_indeterminate_first_decider_moves_on_to_the_next_kind():
    outcomes = [_outcome(0, Verdict.INDETERMINATE, "POLICY:sign-off-policy@1")]
    decision = resolve_gate(_gate(), outcomes, person_required=False)
    assert decision.resolution is GateResolution.NEEDS_AGENT
    assert decision.next_decider_index == 1


def test_every_decider_indeterminate_and_none_left_pauses():
    outcomes = [
        _outcome(0, Verdict.INDETERMINATE, "POLICY:sign-off-policy@1"),
        _outcome(1, Verdict.INDETERMINATE, "AGENT:review-recommendations@1:session-1"),
        _outcome(2, Verdict.INDETERMINATE, "PERSON:nobody-answered"),
    ]
    decision = resolve_gate(_gate(), outcomes, person_required=False)
    assert decision.resolution is GateResolution.PAUSED


def test_no_deciders_declared_at_all_pauses_immediately():
    decision = resolve_gate(_gate(deciders=()), [], person_required=False)
    assert decision.resolution is GateResolution.PAUSED


def test_person_required_ignores_earlier_deny_and_waits_for_a_person():
    # person_required_when true: earlier deciders are recorded but don't count.
    outcomes = [_outcome(0, Verdict.DENY, "POLICY:sign-off-policy@1")]
    decision = resolve_gate(_gate(), outcomes, person_required=True)
    assert decision.resolution is GateResolution.NEEDS_AGENT
    assert decision.next_decider_index == 1


def test_person_required_and_person_has_decided_counts_it():
    outcomes = [
        _outcome(0, Verdict.DENY, "POLICY:sign-off-policy@1"),
        _outcome(1, Verdict.INDETERMINATE, "AGENT:review-recommendations@1:s1"),
        _outcome(2, Verdict.PERMIT, "PERSON:user-42"),
    ]
    decision = resolve_gate(_gate(), outcomes, person_required=True)
    assert decision.resolution is GateResolution.DECIDED
    assert decision.verdict is Verdict.PERMIT


def test_first_of_several_true_deciders_wins_not_a_later_one():
    outcomes = [
        _outcome(0, Verdict.DENY, "POLICY:sign-off-policy@1"),
        _outcome(1, Verdict.PERMIT, "AGENT:review-recommendations@1:s1"),
    ]
    decision = resolve_gate(_gate(), outcomes, person_required=False)
    assert decision.verdict is Verdict.DENY
    assert decision.decided_by.decider_index == 0


def test_evaluate_policy_decider_permits():
    policy = StubPolicyAdapter()
    decider = Decider(kind="policy", ref="sign-off-policy@1")
    outcome = asyncio.run(
        evaluate_policy_decider(
            decider,
            0,
            reviewing={"state": {"recommendations": []}},
            identity="user:iain",
            platform_id="t",
            run_id="r",
            policy=policy,
        )
    )
    assert outcome.verdict is Verdict.PERMIT
    assert outcome.decided_by == "POLICY:sign-off-policy@1"


def test_evaluate_policy_decider_denies():
    policy = StubPolicyAdapter(policy_denies={"sign-off-policy@1"})
    decider = Decider(kind="policy", ref="sign-off-policy@1")
    outcome = asyncio.run(
        evaluate_policy_decider(
            decider,
            0,
            reviewing={},
            identity="user:iain",
            platform_id="t",
            run_id="r",
            policy=policy,
        )
    )
    assert outcome.verdict is Verdict.DENY


def _decision(verdict="PERMIT", evidence=None, rationale="looks good"):
    return {
        "verdict": verdict,
        "rationale": rationale,
        "evidence": evidence
        if evidence is not None
        else [{"path": "state.recommendations", "claim": "ok"}],
    }


def test_agent_decision_with_grounded_evidence_counts():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {"recommendations": [{"id": "r1"}], "confidence": "HIGH"}},
        agent_session_id="session-1",
        produced_by={"state.recommendations": "session-0"},
    )
    assert outcome.verdict is Verdict.PERMIT


def test_agent_decision_with_no_evidence_at_all_is_indeterminate():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(evidence=[]),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {"recommendations": [{"id": "r1"}]}},
        agent_session_id="session-1",
        produced_by={},
    )
    # No grounded evidence -> decision_evidence trivially passes (no findings),
    # but "an agent that returns PERMIT with no grounded evidence cannot pass" —
    # covered by the evidence-existence check below.
    assert outcome.verdict is Verdict.INDETERMINATE


def test_agent_decision_citing_a_path_outside_reviewing_is_indeterminate():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(evidence=[{"path": "state.not_reviewed", "claim": "x"}]),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {"not_reviewed": "value"}},
        agent_session_id="session-1",
        produced_by={},
    )
    assert outcome.verdict is Verdict.INDETERMINATE
    assert "reviewing" in outcome.rationale


def test_agent_decision_citing_a_path_that_does_not_resolve_is_indeterminate():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(evidence=[{"path": "state.recommendations", "claim": "x"}]),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {}},  # recommendations absent
        agent_session_id="session-1",
        produced_by={},
    )
    assert outcome.verdict is Verdict.INDETERMINATE
    assert "resolve" in outcome.rationale


def test_agent_deciding_on_its_own_produced_work_is_indeterminate():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {"recommendations": [{"id": "r1"}], "confidence": "HIGH"}},
        agent_session_id="session-1",
        produced_by={"state.recommendations": "session-1"},  # same session
    )
    assert outcome.verdict is Verdict.INDETERMINATE
    assert "own work" in outcome.rationale


def test_agent_decision_with_verdict_outside_the_vocabulary_is_indeterminate():
    gate = _gate()
    outcome = check_agent_decision(
        _decision(verdict="MAYBE"),
        gate.deciders[1],
        1,
        gate=gate,
        run_state={"state": {"recommendations": [{"id": "r1"}]}},
        agent_session_id="session-1",
        produced_by={},
    )
    assert outcome.verdict is Verdict.INDETERMINATE
    assert "ADR-028" in outcome.rationale
