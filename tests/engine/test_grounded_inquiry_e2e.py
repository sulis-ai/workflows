"""End-to-end pressure test: the spec's own Appendix A worked example
("grounded inquiry, single path, in v1"), loaded from the same fixture and
corpus `test_appendix_a.py` already validates statically, driven through
the real engine (`next()`/`report()`/`decide()`) for every declared branch
this process can actually take.

Before this file, Appendix A had only ever been checked for structural
validity (`test_appendix_a.py`) — never run. Doing so for the first time
found two real engine bugs, both fixed and recorded in the spec's own
decision log: D19 (state reducers other than REPLACE were never
implemented, crashing `report()` on the `gather` step's own `APPEND`
write) and D20 (a loop body spanning more than one hand-off node could
never exhaust its own budget or make progress, stuck re-asking for the
first node forever). These tests are the regression corpus for both, and
the first fixtures to exercise every routing branch Appendix A itself
declares: the REVISED loop at both `after-interrogate` and
`after-fidelity`, the DROPPED short-circuits, the honest INSUFFICIENT
stop, all three `sign-off` decider kinds, and the RECURSIVE stub branch.

One declared branch is deliberately NOT exercised here:
`sign-off.person_required_when: 'state.confidence == "INSUFFICIENT"'` can
never actually evaluate true in a real run of this process, because
`honest-stop` already diverts `INSUFFICIENT` straight to the
`INSUFFICIENT` ending before `recommend`/`check-fidelity`/`sign-off` are
ever reached — found by trying to write that scenario and finding no path
reaches it. The `person_required_when` mechanism itself is still correct
and covered on its own terms by `tests/engine/test_gates.py`; this is
Appendix A's own worked example declaring a condition it can never need,
left as a finding (see the run record) rather than rewritten here, since
fixing the example is outside this pass's scope.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.model import Process
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.claims import StubClaimsAdapter
from sulis_workflows.domain.ports.policy import (
    PolicyDecision,
    StubPolicyAdapter,
    Verdict,
)
from sulis_workflows.domain.ports.records import StubRecordsAdapter
from sulis_workflows.engine.run import (
    AnswerKind,
    EngineContext,
    NextAnswer,
    next_,
    report,
)

BUILTIN = (
    Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition" / "builtin"
)
CORPUS = Path(__file__).parents[1] / "definition" / "fixtures" / "appendix_a_corpus"
APPENDIX_A = (
    Path(__file__).parents[1]
    / "definition"
    / "fixtures"
    / "accepted"
    / "process-appendix-a.yaml"
)

_BUILTIN_FILES = [
    BUILTIN / "control-result.profile.yaml",
    BUILTIN / "decision.profile.yaml",
    BUILTIN / "profile-conformance.tool.yaml",
    BUILTIN / "decision-evidence.tool.yaml",
]
_CORPUS_FILES = sorted(CORPUS.glob("*.yaml"))


def _registry() -> Registry:
    registry = Registry()
    for path in [*_BUILTIN_FILES, *_CORPUS_FILES]:
        registry.add(load_definition_file(path))
    return registry


def _process() -> Process:
    process = load_definition_file(APPENDIX_A)
    assert isinstance(process, Process)
    return process


BRIEF = {"question": "What drove Q3 churn?"}
HOST_INPUTS = {"topology_index": {"docs": ["ticket-1", "survey-1"]}}

# ----------------------------------------------------------------- profile-valid fixtures --

FINDING_1 = {
    "id": "f1",
    "claim": "Cancellation surveys cite pricing changes.",
    "source": "survey-q3",
}
FINDING_2 = {
    "id": "f2",
    "claim": "Support tickets tagged 'price' rose 40% in Q3.",
    "source": "zendesk-q3",
}
INSIGHT_1 = {"id": "i1", "claim": "Pricing changes materially drove Q3 churn."}
INSIGHT_2 = {"id": "i2", "claim": "Support volume corroborates the pricing signal."}
RECOMMENDATION_1 = {
    "id": "r1",
    "action": "Revisit the Q3 pricing tier before Q4 renewal.",
}


# --------------------------------------------------------------------------- test doubles --


@dataclass
class ScriptedCodeToolAdapter:
    """A `CodeToolPort` stub whose response for a given `ref` can vary by
    call count, not just be constant — needed for CODE-mechanism Tools
    that are dispatched more than once in a single run (`converge-confidence`
    inline in a loop's convergence path is always once, but
    `check-recommendation-fidelity` is dispatched once per `after-fidelity`
    loop visit, and this corpus needs different verdicts across those
    visits to drive REVISED-then-exhausted scenarios).

    `static` answers the same response every time; `scripts` consumes one
    response per call for that ref, in order, and refuses (loudly, not
    silently repeating the last one) once a ref is called more times than
    scripted — a silent repeat would hide a scenario that drives more
    loop iterations than the test author intended.
    """

    static: dict[str, dict[str, Any]] = field(default_factory=dict)
    scripts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _counters: dict[str, int] = field(default_factory=dict)

    async def call(
        self, ref: str, inputs: dict[str, Any], *, platform_id: str, run_id: str
    ) -> dict[str, Any]:
        self.calls.append((ref, dict(inputs)))
        if ref in self.scripts:
            seq = self.scripts[ref]
            index = self._counters.get(ref, 0)
            self._counters[ref] = index + 1
            assert index < len(seq), (
                f"{ref!r} called {index + 1} times, more than the {len(seq)} "
                "responses scripted for it"
            )
            return seq[index]
        if ref in self.static:
            return self.static[ref]
        raise AssertionError(
            f"unscripted CODE ref {ref!r} called with inputs {inputs!r}"
        )


@dataclass
class ScriptedPolicyAdapter:
    """`StubPolicyAdapter` answers a fixed verdict per permission/ref for
    the whole test; `sign-off DENY loops back to gather then succeeds on
    retry` needs `evaluate_policy` to answer differently across the two
    times the run asks the same policy ref, which that fixed-set shape
    cannot express — so this scripts `evaluate_policy` by call count,
    the same idea as `ScriptedCodeToolAdapter` above. `authorize` (every
    other permission check in the run — dispatch, decide, process start)
    stays a plain permit-everything default, since no scenario here needs
    it to do otherwise.
    """

    evaluate_policy_scripts: dict[str, list[Verdict]] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    async def authorize(
        self, permission: str, *, identity: str, platform_id: str, run_id: str
    ) -> PolicyDecision:
        return PolicyDecision(verdict=Verdict.PERMIT)

    async def evaluate_policy(
        self,
        ref: str,
        *,
        reviewing: dict[str, Any],
        identity: str,
        platform_id: str,
        run_id: str,
    ) -> PolicyDecision:
        if ref in self.evaluate_policy_scripts:
            seq = self.evaluate_policy_scripts[ref]
            index = self._counters.get(ref, 0)
            self._counters[ref] = (
                min(index + 1, len(seq) - 1) if index + 1 >= len(seq) else index + 1
            )
            verdict = seq[min(index, len(seq) - 1)]
            return PolicyDecision(
                verdict=verdict, rationale=f"scripted:{verdict.value}"
            )
        return PolicyDecision(verdict=Verdict.PERMIT)


def _checker_passes() -> dict[str, dict[str, Any]]:
    return {
        "appendix_a_corpus.checkers:output_present": {
            "result": {"passed": True, "findings": []}
        },
        "appendix_a_corpus.checkers:check_entailment": {
            "result": {"passed": True, "findings": []}
        },
    }


def _run(coro):
    return asyncio.run(coro)


def _ctx(
    registry: Registry,
    code_tool: ScriptedCodeToolAdapter,
    records: StubRecordsAdapter,
    claims: StubClaimsAdapter,
    *,
    policy=None,
    identity: str = "agent:driver",
) -> EngineContext:
    """A fresh `EngineContext` wrapping the same backing stores every call —
    §12.1's "starting and resuming are the same call, nothing held in
    memory" contract: it is the stores, not the context object, that carry
    a run's state between calls."""
    return EngineContext(
        policy=policy or StubPolicyAdapter(),
        code_tool=code_tool,
        records=records,
        claims=claims,
        registry=registry,
        identity=identity,
        platform_id="tenant-1",
    )


def _drive(
    process: Process,
    run_id: str,
    registry: Registry,
    code_tool: ScriptedCodeToolAdapter,
    records: StubRecordsAdapter,
    claims: StubClaimsAdapter,
    *,
    policy=None,
    respond,
    max_calls: int = 40,
) -> NextAnswer:
    """Drives one run from `next()` to an `ENDED` answer. `respond(answer,
    ctx_factory)` decides how to answer one hand-off (a `report()` or
    `decide()` call) and returns the resulting `NextAnswer`; `ctx_factory`
    is a zero-arg callable making a fresh context over the same stores, so
    `respond` can pick whichever identity a given call needs (e.g. the
    reviewing agent for a GATE's `agent` decider)."""

    def ctx_factory(identity: str = "agent:driver") -> EngineContext:
        return _ctx(
            registry, code_tool, records, claims, policy=policy, identity=identity
        )

    answer = _run(
        next_(
            process,
            run_id,
            "root",
            ctx_factory(),
            inputs={"brief": BRIEF},
            host_inputs=HOST_INPUTS,
        )
    )
    calls = 0
    while answer.kind is not AnswerKind.ENDED:
        calls += 1
        assert calls <= max_calls, (
            f"did not reach an ending within {max_calls} calls; stuck at {answer!r}"
        )
        answer = respond(answer, ctx_factory)
    return answer


def _report(process, run_id, answer, ctx, *, output):
    return _run(
        report(
            process,
            run_id,
            answer.scope or "root",
            answer.node_id,
            ctx,
            inputs={"brief": BRIEF},
            host_inputs=HOST_INPUTS,
            output=output,
        )
    )


# ---------------------------------------------------------------------------- scenarios --


def test_single_path_happy_run_reaches_complete_via_policy_permit() -> None:
    """1: SINGLE path, one finding round, SURVIVED, GROUNDED confidence,
    ENTAILED recommendations, sign-off's own `policy` decider PERMITs —
    the shortest real path through the whole process, no loop taken."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
            "appendix_a_corpus.tools:converge_confidence": {"confidence": "GROUNDED"},
            "appendix_a_corpus.tools:conclude": {
                "conclusion": {"summary": "Pricing changes materially drove Q3 churn."}
            },
            "appendix_a_corpus.tools:check_recommendation_fidelity": {
                "recommendations": [RECOMMENDATION_1],
                "verdict": "ENTAILED",
            },
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()
    gather_calls = 0
    interrogate_calls = 0
    recommend_calls = 0

    def respond(answer: NextAnswer, ctx_factory):
        nonlocal gather_calls, interrogate_calls, recommend_calls
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            gather_calls += 1
            return _report(
                process,
                "run-e2e-1",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1, FINDING_2]},
            )
        if answer.node_id == "interrogate":
            interrogate_calls += 1
            return _report(
                process,
                "run-e2e-1",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "SURVIVED"},
            )
        if answer.node_id == "recommend":
            recommend_calls += 1
            return _report(
                process,
                "run-e2e-1",
                answer,
                ctx_factory(),
                output={"recommendations": [RECOMMENDATION_1]},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process, "run-e2e-1", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "COMPLETE"
    assert final.outcome == "SUCCESS"
    assert gather_calls == 1
    assert interrogate_calls == 1
    assert recommend_calls == 1


def test_interrogate_revised_loop_exhausts_its_budget_and_still_converges() -> None:
    """2 (D20's own regression, against the real process rather than a
    synthetic one): `after-interrogate`'s REVISED loop has `budget: 2` —
    `gather`/`interrogate` are both SKILL hand-offs, so this is the exact
    shape D20 fixed (a loop body spanning two separate hand-off calls).
    REVISED every time exhausts the budget on the third asking and falls
    through to `converge` via `on_exhausted`, rather than looping forever
    or stalling on `gather`."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
            "appendix_a_corpus.tools:converge_confidence": {"confidence": "PARTIAL"},
            "appendix_a_corpus.tools:conclude": {
                "conclusion": {"summary": "Partial evidence of a pricing effect."}
            },
            "appendix_a_corpus.tools:check_recommendation_fidelity": {
                "recommendations": [RECOMMENDATION_1],
                "verdict": "ENTAILED",
            },
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()
    gather_calls = 0
    interrogate_calls = 0

    def respond(answer: NextAnswer, ctx_factory):
        nonlocal gather_calls, interrogate_calls
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            gather_calls += 1
            return _report(
                process,
                "run-e2e-2",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            interrogate_calls += 1
            return _report(
                process,
                "run-e2e-2",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "REVISED"},
            )
        if answer.node_id == "recommend":
            return _report(
                process,
                "run-e2e-2",
                answer,
                ctx_factory(),
                output={"recommendations": [RECOMMENDATION_1]},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process, "run-e2e-2", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "COMPLETE"
    # budget=2 permits 2 loop-backs: interrogate asked 3 times (REVISED each
    # time), the 3rd exhausting the budget and falling through to converge;
    # gather is asked once per interrogate asking (3 times), never a 4th.
    assert interrogate_calls == 3
    assert gather_calls == 3


def test_interrogate_dropped_ends_the_run_dropped_with_no_loop_taken() -> None:
    """3: `after-interrogate`'s DROPPED branch ends the run immediately —
    no loop, no `converge`/`conclude` ever reached."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()

    def respond(answer: NextAnswer, ctx_factory):
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            return _report(
                process,
                "run-e2e-3",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            return _report(
                process,
                "run-e2e-3",
                answer,
                ctx_factory(),
                output={"insights": [], "verdict": "DROPPED"},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process, "run-e2e-3", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "DROPPED"
    assert final.outcome == "SUCCESS"
    # converge/conclude are CODE Tools that would have been dispatched
    # inline had the run reached them — confirming they weren't is the
    # same as confirming the run never got past `after-interrogate`.
    called_refs = {ref for ref, _ in code_tool.calls}
    assert "appendix_a_corpus.tools:converge_confidence" not in called_refs
    assert "appendix_a_corpus.tools:conclude" not in called_refs


def test_insufficient_confidence_stops_honestly_before_ever_recommending() -> None:
    """4: `honest-stop` ends the run `INSUFFICIENT` (a declared `SUCCESS`
    outcome, per spec — an honest stop is not a failure) without ever
    reaching `recommend` — the same finding that makes `sign-off`'s own
    `person_required_when` unreachable in this worked example (module
    docstring)."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
            "appendix_a_corpus.tools:converge_confidence": {
                "confidence": "INSUFFICIENT"
            },
            "appendix_a_corpus.tools:conclude": {
                "conclusion": {"summary": "The evidence does not support an answer."}
            },
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()

    def respond(answer: NextAnswer, ctx_factory):
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            return _report(
                process,
                "run-e2e-4",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            return _report(
                process,
                "run-e2e-4",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "SURVIVED"},
            )
        raise AssertionError(
            f"unexpected hand-off: {answer.node_id!r} — recommend must not be reached"
        )

    final = _drive(
        process, "run-e2e-4", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "INSUFFICIENT"
    assert final.outcome == "SUCCESS"


def test_fidelity_revised_loop_exhausts_its_budget_and_drops() -> None:
    """5: `after-fidelity`'s REVISED loop (budget 2, `on_exhausted: end
    DROPPED` — unlike `after-interrogate`, exhaustion here is terminal,
    not a fallthrough). `recommend` (SKILL, hand-off) and
    `check-recommendation-fidelity` (CODE, inline) alternate inside the
    loop body — a hand-off/inline mix distinct from D20's two-hand-off
    shape, exercised here for its own sake."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
            "appendix_a_corpus.tools:converge_confidence": {"confidence": "GROUNDED"},
            "appendix_a_corpus.tools:conclude": {
                "conclusion": {"summary": "Pricing changes drove Q3 churn."}
            },
        },
        scripts={
            "appendix_a_corpus.tools:check_recommendation_fidelity": [
                {"recommendations": [RECOMMENDATION_1], "verdict": "REVISED"},
                {"recommendations": [RECOMMENDATION_1], "verdict": "REVISED"},
                {"recommendations": [RECOMMENDATION_1], "verdict": "REVISED"},
            ]
        },
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()
    recommend_calls = 0

    def respond(answer: NextAnswer, ctx_factory):
        nonlocal recommend_calls
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            return _report(
                process,
                "run-e2e-5",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            return _report(
                process,
                "run-e2e-5",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "SURVIVED"},
            )
        if answer.node_id == "recommend":
            recommend_calls += 1
            return _report(
                process,
                "run-e2e-5",
                answer,
                ctx_factory(),
                output={"recommendations": [RECOMMENDATION_1]},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process, "run-e2e-5", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "DROPPED"
    assert final.outcome == "SUCCESS"
    assert recommend_calls == 3


def test_sign_off_policy_indeterminate_falls_to_agent_decider_permit() -> None:
    """6: `sign-off`'s deciders are asked in order (policy, agent, person,
    §7.6) — a policy `INDETERMINATE` is "not my call" (ADR-028, D4) and
    passes to the next decider rather than ending the run; the `agent`
    decider (`review-recommendations@1`, a SKILL Tool) then hands off as
    `DECISION_STEP`, and a `PERMIT` with evidence citing one of the gate's
    own `reviewing` paths resolves it.

    The reviewing hand-off uses a distinct identity (`agent:reviewer`, not
    the driver's own `agent:driver`) deliberately: §7.6's "no deciding on
    your own work" check (`gates.py::check_agent_decision`) refuses a
    decider whose identity produced any of the gate's own `reviewing`
    values, and `recommend` (which `agent:driver` performs, `AGENT:...`-
    attributed) writes `state.recommendations` before `check-fidelity`
    (CODE) overwrites it — found by first trying this scenario with one
    shared identity throughout and getting an unexpected INDETERMINATE.
    `produced_by` only ever records an AGENT-attributed write and is never
    cleared by a later CODE-attributed one, so it still names `agent:driver`
    as `state.recommendations`'s producer even though a CODE Tool computed
    its actual final value — a real provenance edge case, left as a finding
    (see the run record) rather than changed here, since which behaviour is
    "more correct" is a product judgement call, not an engine bug."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
            "appendix_a_corpus.tools:converge_confidence": {"confidence": "GROUNDED"},
            "appendix_a_corpus.tools:conclude": {
                "conclusion": {"summary": "Pricing changes drove Q3 churn."}
            },
            "appendix_a_corpus.tools:check_recommendation_fidelity": {
                "recommendations": [RECOMMENDATION_1],
                "verdict": "ENTAILED",
            },
        }
    )
    policy = ScriptedPolicyAdapter(
        evaluate_policy_scripts={"grounded-inquiry-sign-off@1": [Verdict.INDETERMINATE]}
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()

    def respond(answer: NextAnswer, ctx_factory):
        if answer.kind is AnswerKind.DECISION_STEP:
            assert answer.node_id == "sign-off"
            return _report(
                process,
                "run-e2e-6",
                answer,
                ctx_factory("agent:reviewer"),
                output={
                    "verdict": "PERMIT",
                    "evidence": [{"path": "state.conclusion"}],
                    "rationale": "The conclusion is grounded and the recommendation follows from it.",
                },
            )
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            return _report(
                process,
                "run-e2e-6",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            return _report(
                process,
                "run-e2e-6",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "SURVIVED"},
            )
        if answer.node_id == "recommend":
            return _report(
                process,
                "run-e2e-6",
                answer,
                ctx_factory(),
                output={"recommendations": [RECOMMENDATION_1]},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process,
        "run-e2e-6",
        registry,
        code_tool,
        records,
        claims,
        policy=policy,
        respond=respond,
    )
    assert final.ending == "COMPLETE"
    assert final.outcome == "SUCCESS"


def test_sign_off_deny_loops_back_to_gather_then_permits_on_retry() -> None:
    """7: `sign-off`'s `DENY` route (`on: { DENY: { next: gather } }`, no
    `loop:` declared — an intentionally unbounded revisit, §7.6's own
    worked example) sends the run all the way back to `gather`; a full
    second pass through `gather`/`interrogate`/`converge`/`conclude`/
    `recommend`/`check-fidelity` then reaches `sign-off` again, where the
    same policy ref now `PERMIT`s."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
        },
        scripts={
            "appendix_a_corpus.tools:converge_confidence": [
                {"confidence": "GROUNDED"},
                {"confidence": "GROUNDED"},
            ],
            "appendix_a_corpus.tools:conclude": [
                {
                    "conclusion": {
                        "summary": "First pass: pricing changes drove Q3 churn."
                    }
                },
                {
                    "conclusion": {
                        "summary": "Second pass: pricing changes drove Q3 churn."
                    }
                },
            ],
            "appendix_a_corpus.tools:check_recommendation_fidelity": [
                {"recommendations": [RECOMMENDATION_1], "verdict": "ENTAILED"},
                {"recommendations": [RECOMMENDATION_1], "verdict": "ENTAILED"},
            ],
        },
    )
    policy = ScriptedPolicyAdapter(
        evaluate_policy_scripts={
            "grounded-inquiry-sign-off@1": [Verdict.DENY, Verdict.PERMIT]
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()
    gather_calls = 0

    def respond(answer: NextAnswer, ctx_factory):
        nonlocal gather_calls
        assert answer.kind is AnswerKind.TOOL_STEP, answer
        if answer.node_id == "gather":
            gather_calls += 1
            return _report(
                process,
                "run-e2e-7",
                answer,
                ctx_factory(),
                output={"findings": [FINDING_1]},
            )
        if answer.node_id == "interrogate":
            return _report(
                process,
                "run-e2e-7",
                answer,
                ctx_factory(),
                output={"insights": [INSIGHT_1], "verdict": "SURVIVED"},
            )
        if answer.node_id == "recommend":
            return _report(
                process,
                "run-e2e-7",
                answer,
                ctx_factory(),
                output={"recommendations": [RECOMMENDATION_1]},
            )
        raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")

    final = _drive(
        process,
        "run-e2e-7",
        registry,
        code_tool,
        records,
        claims,
        policy=policy,
        respond=respond,
        max_calls=60,
    )
    assert final.ending == "COMPLETE"
    assert final.outcome == "SUCCESS"
    assert gather_calls == 2


def test_recursive_path_stub_ends_dropped() -> None:
    """8: `choose-path`'s other branch — Appendix A's own RECURSIVE path is
    a stub (`decompose` just ends DROPPED; the spec's own text says "the
    recursive path is not shown"), exercised here only to confirm
    `choose-path`'s ROUTE itself takes it correctly, not to claim anything
    about a real recursive-inquiry Tool set (none exists)."""
    registry = _registry()
    process = _process()
    code_tool = ScriptedCodeToolAdapter(
        static={
            **_checker_passes(),
            "appendix_a_corpus.tools:classify_inquiry": {"path": "RECURSIVE"},
            "appendix_a_corpus.tools:frame_question": {
                "framed_question": "What drove Q3 churn?"
            },
        }
    )
    records = StubRecordsAdapter()
    claims = StubClaimsAdapter()

    def respond(answer: NextAnswer, ctx_factory):
        raise AssertionError(
            f"unexpected hand-off: {answer.node_id!r} — decompose is CODE-only, no hand-off"
        )

    final = _drive(
        process, "run-e2e-8", registry, code_tool, records, claims, respond=respond
    )
    assert final.ending == "DROPPED"
    assert final.outcome == "SUCCESS"
