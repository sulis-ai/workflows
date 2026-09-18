"""GATE execution — spec §7.6 (reaching a decision), WP-02 step 4.

Deciders are asked in order; the first `PERMIT` or `DENY` decides
(§7.6). Of the three decider kinds, only `policy` is engine-run —
deterministic, via `PolicyPort.evaluate_policy` — the same split §12.1
draws for STEP mechanisms (§10.2's CODE/EXTERNAL/deterministic-PROCESS
vs. SKILL/non-deterministic PROCESS). An `agent` decider is a
non-deterministic Tool (`SKILL`) and a `person` decider is always a
hand-off; both
need a round trip through `next()`/`report()`/`decide()` (WP-02 step 5),
so this module never dispatches them itself. `resolve_gate` is pure and
synchronous: given the deciders already asked and answered (in whatever
order they were resolved across however many `next()`/`report()` calls
that took), it says either the gate is decided, or which kind of decider
needs asking next.

`check_agent_decision` implements the half of §7.6's evidence check that
`definition/checkers.py`'s `decision_evidence` explicitly leaves undone
in its own docstring — that every `evidence[].path` also *resolves to a
value in the run*, not just that it names one of the gate's `reviewing`
paths — plus the separation-of-duty check, since both need live run
state and decider identity that a pure checker Tool is never given.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sulis_workflows.definition import checkers
from sulis_workflows.definition.expressions import evaluate, parse
from sulis_workflows.definition.model import Decider, GateNode
from sulis_workflows.domain.ports.policy import PolicyPort, Verdict

__all__ = [
    "DeciderOutcome",
    "GateDecision",
    "GateResolution",
    "check_agent_decision",
    "evaluate_policy_decider",
    "resolve_gate",
]


@dataclass(frozen=True)
class DeciderOutcome:
    """§7.6's provenance record for one decider actually asked: the
    verdict, `decided_by`, the rationale, the evidence, and which decider
    (by index into `node.deciders`) this was. Time and "which asking of
    the gate" belong to the durable record (§12.2) the caller writes —
    this is the in-memory shape before it is persisted.
    """

    decider_index: int
    verdict: Verdict
    decided_by: str  # "POLICY:<id>" | "AGENT:<tool>@<v>:<session>" | "PERSON:<subject>"
    rationale: str | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()


class GateResolution(str, Enum):
    DECIDED = "DECIDED"
    NEEDS_POLICY = "NEEDS_POLICY"
    NEEDS_AGENT = "NEEDS_AGENT"
    NEEDS_PERSON = "NEEDS_PERSON"
    PAUSED = "PAUSED"


@dataclass(frozen=True)
class GateDecision:
    resolution: GateResolution
    verdict: Verdict | None = None
    decided_by: DeciderOutcome | None = None
    outcomes: tuple[DeciderOutcome, ...] = ()
    next_decider_index: int | None = None


_RESOLUTION_FOR_KIND = {
    "policy": GateResolution.NEEDS_POLICY,
    "agent": GateResolution.NEEDS_AGENT,
    "person": GateResolution.NEEDS_PERSON,
}


def resolve_gate(
    node: GateNode,
    outcomes: Sequence[DeciderOutcome],
    *,
    person_required: bool,
) -> GateDecision:
    """§7.6: "Deciders are asked in order; the first `PERMIT` or `DENY`
    decides." `person_required_when`: "while true, deciders before the
    first person are still asked and recorded, but only a person's
    verdict counts" — `outcomes` still carries every decider asked
    either way; this function is what applies that filter.

    Pure and synchronous — never calls a port. `outcomes` is exactly the
    deciders already asked and answered, in order. Where it is shorter
    than `node.deciders`, the next undecided decider's kind says what the
    caller must do before calling this again with one more outcome
    appended.
    """
    countable = (
        outcomes
        if not person_required
        else tuple(o for o in outcomes if o.decided_by.startswith("PERSON:"))
    )
    for outcome in countable:
        if outcome.verdict is not Verdict.INDETERMINATE:
            return GateDecision(
                resolution=GateResolution.DECIDED,
                verdict=outcome.verdict,
                decided_by=outcome,
                outcomes=tuple(outcomes),
            )

    deciders = node.deciders
    if len(outcomes) < len(deciders):
        next_decider = deciders[len(outcomes)]
        return GateDecision(
            resolution=_RESOLUTION_FOR_KIND[next_decider.kind],
            outcomes=tuple(outcomes),
            next_decider_index=len(outcomes),
        )

    # Every declared decider has answered (or none were declared at all)
    # and none decided — §7.6: "the gate stays open for a person with the
    # gate's permission" (pause).
    return GateDecision(resolution=GateResolution.PAUSED, outcomes=tuple(outcomes))


async def evaluate_policy_decider(
    decider: Decider,
    decider_index: int,
    *,
    reviewing: Mapping[str, Any],
    identity: str,
    platform_id: str,
    run_id: str,
    policy: PolicyPort,
) -> DeciderOutcome:
    """§7.6: "The host's `PolicyPort` evaluates the policy (trust earned,
    thresholds, grants)." `decider.ref` names the `POLICY`-kind Control.
    """
    assert decider.ref is not None  # V9 requires `policy: <ref>` to declare one
    decision = await policy.evaluate_policy(
        decider.ref,
        reviewing=reviewing,
        identity=identity,
        platform_id=platform_id,
        run_id=run_id,
    )
    return DeciderOutcome(
        decider_index=decider_index,
        verdict=decision.verdict,
        decided_by=f"POLICY:{decider.ref}",
        rationale=decision.rationale,
    )


def check_agent_decision(
    decision: Mapping[str, Any],
    decider: Decider,
    decider_index: int,
    *,
    gate: GateNode,
    run_state: Mapping[str, Any],
    agent_session_id: str,
    produced_by: Mapping[str, str],
) -> DeciderOutcome:
    """§7.6: "An agent decision is checked before it counts" — every
    `evidence[].path` must be one of the gate's `reviewing` paths
    (`checkers.decision_evidence`) AND resolve to a value in the run (the
    half that checker's own docstring leaves for the engine, since only
    the engine holds run state). Also: "No deciding on your own work"
    (§7.6, ANSI INCITS 359-2004) — the deciding session must not be
    whichever produced any of the gate's `reviewing` values.

    A decision failing any of these, or whose `verdict` is not one of the
    three ADR-028 values (D13's reading of "outside its `may` list"),
    counts as `INDETERMINATE` rather than raising.
    """
    decided_by = f"AGENT:{decider.ref}:{agent_session_id}"
    evidence = tuple(decision.get("evidence", ()))
    rationale = decision.get("rationale")

    try:
        verdict = Verdict(decision.get("verdict"))
    except ValueError:
        return DeciderOutcome(
            decider_index=decider_index,
            verdict=Verdict.INDETERMINATE,
            decided_by=decided_by,
            rationale=(
                f"decider returned {decision.get('verdict')!r}, outside the "
                "ADR-028 vocabulary (D13)."
            ),
            evidence=evidence,
        )

    if verdict is Verdict.PERMIT and not evidence:
        # "An agent that returns PERMIT with no grounded evidence cannot pass" (§7.6).
        return DeciderOutcome(
            decider_index=decider_index,
            verdict=Verdict.INDETERMINATE,
            decided_by=decided_by,
            rationale="PERMIT with no evidence cited — cannot pass ungrounded.",
        )

    checked = checkers.decision_evidence(decision, "decision@1", gate.reviewing)
    if not checked["passed"]:
        return DeciderOutcome(
            decider_index=decider_index,
            verdict=Verdict.INDETERMINATE,
            decided_by=decided_by,
            rationale="evidence cites a path outside the gate's `reviewing` list.",
            evidence=evidence,
        )

    for item in evidence:
        path = item.get("path") if isinstance(item, Mapping) else None
        if path is None or evaluate(parse(path), run_state) is None:
            return DeciderOutcome(
                decider_index=decider_index,
                verdict=Verdict.INDETERMINATE,
                decided_by=decided_by,
                rationale=f"evidence path {path!r} does not resolve to a value in this run.",
                evidence=evidence,
            )

    for path in gate.reviewing:
        if produced_by.get(path) == agent_session_id:
            return DeciderOutcome(
                decider_index=decider_index,
                verdict=Verdict.INDETERMINATE,
                decided_by=decided_by,
                rationale=(
                    f"decider {agent_session_id!r} produced {path!r}, one of this "
                    "gate's own reviewing values — no deciding on your own work."
                ),
                evidence=evidence,
            )

    return DeciderOutcome(
        decider_index=decider_index,
        verdict=verdict,
        decided_by=decided_by,
        rationale=rationale,
        evidence=evidence,
    )
