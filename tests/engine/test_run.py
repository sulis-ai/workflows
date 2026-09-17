"""next()/report()/decide() — the stateless engine contract (spec §12.1, WP-02 step 5).

Builds a small real Process (STEP -> ROUTE -> GATE(policy) -> end) from
model.py dataclasses directly and drives it through a fresh EngineContext
on every call — proving the "starting and resuming are the same call,
nothing held in memory" property by using a brand new EngineContext
(same backing stub stores) for each call rather than reusing one object
across the whole run.
"""

from __future__ import annotations

import asyncio

from sulis_workflows.definition.model import (
    Decider,
    Ending,
    ErrorSpec,
    GateNode,
    Header,
    InputSpec,
    Mechanism,
    OutputSpec,
    Process,
    RouteNode,
    RouteOption,
    RouteTarget,
    StepNode,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.claims import StubClaimsAdapter
from sulis_workflows.domain.ports.code_tool import (
    StubCodeToolAdapter,
    ToolTransientError,
)
from sulis_workflows.domain.ports.policy import StubPolicyAdapter, Verdict
from sulis_workflows.domain.ports.records import StubRecordsAdapter
from sulis_workflows.engine.run import AnswerKind, EngineContext, decide, next_, report


def _header(id_: str, kind: str) -> Header:
    return Header(
        api_version="sulis.workflows/v1", kind=kind, id=id_, version="1.0.0", title=id_
    )


def _classify_tool() -> Tool:
    return Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:classify"),
        effect="QUERY",
        inputs={"question": InputSpec(type="string")},
        permission="workflows.classify.dispatch",
        errors=(ErrorSpec(code="FLAKY", error_class="TRANSIENT"),),
    )


def _process(**overrides) -> Process:
    defaults = {
        "header": _header("small-process", "PROCESS"),
        "start": "classify",
        "permission": "workflows.small-process.start",
        "nodes": {
            "classify": StepNode(
                id="classify",
                tool="classify@1",
                in_={"question": "inputs.question"},
                out={"verdict": "state.verdict"},
                next="after-classify",
                on_error={"FLAKY": RouteTarget(end="FAILED_FLAKY")},
            ),
            "after-classify": RouteNode(
                id="after-classify",
                when=(
                    RouteOption(if_='state.verdict == "A"', next="sign-off"),
                    RouteOption(if_='state.verdict == "B"', end="DROPPED"),
                ),
            ),
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="policy", ref="sign-off-policy@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        },
        "endings": {
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "DROPPED": Ending(outcome="SUCCESS", says="Dropped."),
            "DENIED": Ending(outcome="STOPPED", says="Denied."),
            "FAILED_FLAKY": Ending(outcome="FAILURE", says="Too flaky."),
        },
    }
    defaults.update(overrides)
    return Process(**defaults)


def _fresh_ctx(records=None, claims=None, policy=None, code_tool=None) -> EngineContext:
    return EngineContext(
        policy=policy or StubPolicyAdapter(),
        code_tool=code_tool
        or StubCodeToolAdapter(responses={"mod:classify": {"verdict": "A"}}),
        records=records if records is not None else StubRecordsAdapter(),
        claims=claims if claims is not None else StubClaimsAdapter(),
        registry=Registry([_classify_tool()]),
        identity="user:iain",
        platform_id="tenant-1",
    )


def _run(coro):
    return asyncio.run(coro)


def test_full_run_reaches_complete_via_step_route_gate():
    records = StubRecordsAdapter()
    process = _process()

    # Each call gets a brand-new EngineContext wrapping the SAME backing
    # stub stores — proving nothing is held in memory between calls, only
    # in the (shared, durable) records/claims stores.
    answer = _run(
        next_(
            process,
            "run-1",
            "root",
            _fresh_ctx(records=records),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_permission_denied_ends_forbidden():
    process = _process()
    policy = StubPolicyAdapter(denies={"workflows.small-process.start"})
    answer = _run(
        next_(
            process,
            "run-2",
            "root",
            _fresh_ctx(policy=policy),
            inputs={},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_process_with_no_permission_refuses_to_start():
    process = _process(permission=None)
    answer = _run(
        next_(process, "run-3", "root", _fresh_ctx(), inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_route_takes_the_b_branch_to_dropped():
    records = StubRecordsAdapter()
    code_tool = StubCodeToolAdapter(responses={"mod:classify": {"verdict": "B"}})
    answer = _run(
        next_(
            _process(),
            "run-4",
            "root",
            _fresh_ctx(records=records, code_tool=code_tool),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.ending == "DROPPED"


def test_gate_policy_deny_routes_to_denied():
    policy = StubPolicyAdapter(policy_denies={"sign-off-policy@1"})
    answer = _run(
        next_(
            _process(),
            "run-5",
            "root",
            _fresh_ctx(policy=policy),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.ending == "DENIED"


def test_gate_with_only_an_agent_decider_hands_off_as_decision_step():
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="agent", ref="review@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    answer = _run(
        next_(
            process,
            "run-6",
            "root",
            _fresh_ctx(),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.DECISION_STEP
    assert answer.node_id == "sign-off"


def test_gate_with_only_a_person_decider_awaits_decision():
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="person", permission="approve.thing"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    answer = _run(
        next_(
            process,
            "run-7",
            "root",
            _fresh_ctx(),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.AWAITING_DECISION
    assert answer.node_id == "sign-off"


def test_decide_completes_a_person_gate_and_the_run_reaches_complete():
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="person", permission="approve.thing"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    records = StubRecordsAdapter()
    ctx = _fresh_ctx(records=records)
    first = _run(
        next_(process, "run-8", "root", ctx, inputs={"question": "why"}, host_inputs={})
    )
    assert first.kind is AnswerKind.AWAITING_DECISION

    second = _run(
        decide(
            process,
            "run-8",
            "root",
            "sign-off",
            _fresh_ctx(records=records),
            inputs={"question": "why"},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note="looks fine",
            subject="user-42",
        )
    )
    assert second.kind is AnswerKind.ENDED
    assert second.ending == "COMPLETE"


def test_step_with_skill_mechanism_hands_off_as_tool_step_then_report_completes_it():
    agentic_tool = Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(),
        mechanism=Mechanism(kind="AGENTIC", ref="skills/classify"),
        effect="QUERY",
        inputs={"question": InputSpec(type="string")},
        permission="workflows.classify.dispatch",
    )
    process = _process()
    records = StubRecordsAdapter()
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([agentic_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    first = _run(
        next_(process, "run-9", "root", ctx, inputs={"question": "why"}, host_inputs={})
    )
    assert first.kind is AnswerKind.TOOL_STEP
    assert first.node_id == "classify"

    ctx2 = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([agentic_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    second = _run(
        report(
            process,
            "run-9",
            "root",
            "classify",
            ctx2,
            inputs={"question": "why"},
            host_inputs={},
            output={"verdict": "A"},
        )
    )
    assert second.kind is AnswerKind.ENDED
    assert second.ending == "COMPLETE"


def test_transient_error_retries_then_succeeds():
    process = _process()
    records = StubRecordsAdapter()
    code_tool = StubCodeToolAdapter()
    call_count = {"n": 0}

    class FlakyThenOkAdapter:
        def __init__(self):
            self.identity = code_tool.identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ToolTransientError("FLAKY")
            return {"verdict": "A"}

    ctx = _fresh_ctx(records=records, code_tool=FlakyThenOkAdapter())
    answer = _run(
        next_(
            process, "run-10", "root", ctx, inputs={"question": "why"}, host_inputs={}
        )
    )
    assert answer.ending == "COMPLETE"
    assert call_count["n"] == 2


def test_mutation_step_second_caller_told_step_running():
    mutating_tool = Tool(
        header=_header("send", "TOOL"),
        output={"sent": OutputSpec(type="boolean")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:send"),
        effect="SIDE_EFFECT",
        permission="workflows.send.dispatch",
    )
    process = _process(
        start="send-step",
        nodes={
            "send-step": StepNode(
                id="send-step", tool="send@1", in_={}, out={}, end="COMPLETE"
            ),
        },
    )
    claims = StubClaimsAdapter()
    records = StubRecordsAdapter()
    registry = Registry([mutating_tool])

    async def _acquire_first():
        from sulis_workflows.domain.ports.records import AttemptKey

        await claims.acquire(
            AttemptKey(run="run-11", scope="root", node="send-step", attempt=1),
            lease_seconds=300,
            claimed_by="someone-else",
            platform_id="tenant-1",
            run_id="run-11",
        )

    _run(_acquire_first())

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=claims,
        registry=registry,
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-11", "root", ctx, inputs={}, host_inputs={}))
    assert answer.kind is AnswerKind.STEP_RUNNING


def test_route_loop_budget_is_enforced_across_revisits():
    from sulis_workflows.definition.model import Ending, LoopSpec

    process = Process(
        header=_header("loopy-process", "PROCESS"),
        start="loopy",
        permission="workflows.loopy.start",
        nodes={
            "loopy": RouteNode(
                id="loopy",
                when=(
                    RouteOption(
                        if_="true",
                        next="loopy",
                        loop=LoopSpec(
                            budget=2, on_exhausted=RouteTarget(end="LOOP_DONE")
                        ),
                    ),
                ),
            ),
        },
        endings={"LOOP_DONE": Ending(outcome="SUCCESS", says="Loop finished.")},
    )
    answer = _run(
        next_(process, "run-loop-1", "root", _fresh_ctx(), inputs={}, host_inputs={})
    )
    assert answer.ending == "LOOP_DONE"


def test_step_revisited_via_a_loop_gets_a_fresh_dispatch_each_time():
    # A STEP looped back to by a ROUTE must be re-dispatched each visit,
    # not resolved from a stale prior-visit record (the same class of bug
    # the ROUTE self-loop test above exists to catch, on the STEP side).
    from sulis_workflows.definition.model import LoopSpec

    tally_tool = Tool(
        header=_header("tally", "TOOL"),
        output={"count": OutputSpec(type="integer")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:tally"),
        effect="QUERY",
        permission="workflows.tally.dispatch",
    )
    process = Process(
        header=_header("tally-process", "PROCESS"),
        start="tally",
        permission="workflows.tally.start",
        nodes={
            "tally": StepNode(id="tally", tool="tally@1", in_={}, out={}, next="check"),
            "check": RouteNode(
                id="check",
                when=(
                    RouteOption(
                        if_="true",
                        next="tally",
                        loop=LoopSpec(budget=2, on_exhausted=RouteTarget(end="DONE")),
                    ),
                ),
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done tallying.")},
    )

    call_count = {"n": 0}

    class CountingAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            return {"count": call_count["n"]}

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=CountingAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tally_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-loop-2", "root", ctx, inputs={}, host_inputs={}))
    assert answer.ending == "DONE"
    assert call_count["n"] == 3  # budget=2 allows 2 loop-backs -> 3 dispatches total
