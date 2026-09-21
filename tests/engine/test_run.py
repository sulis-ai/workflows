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

import pytest

from sulis_workflows.definition.model import (
    ControlRef,
    Decider,
    Ending,
    ErrorSpec,
    GateNode,
    Header,
    InputSpec,
    LoopSpec,
    Mechanism,
    OutputSpec,
    Process,
    ProcessDefaults,
    RetrySpec,
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
from sulis_workflows.domain.ports.policy import (
    PolicyDecision,
    StubPolicyAdapter,
    Verdict,
)
from sulis_workflows.domain.ports.records import (
    AttemptKey,
    AttemptRecord,
    StubRecordsAdapter,
)
from sulis_workflows.engine.run import (
    AnswerKind,
    EngineContext,
    EngineRefusal,
    decide,
    next_,
    report,
    skip,
)


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


def _produce_tool(permission: str | None = "workflows.produce.dispatch") -> Tool:
    return Tool(
        header=_header("produce", "TOOL"),
        output={"recommendation": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/produce"),
        effect="QUERY",
        inputs={},
        permission=permission,
    )


def _review_tool(permission: str | None = "workflows.review.dispatch") -> Tool:
    return Tool(
        header=_header("review", "TOOL"),
        output={"decision": OutputSpec(type="any")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/review"),
        effect="QUERY",
        inputs={},
        permission=permission,
    )


def _agent_gate_process() -> Process:
    return Process(
        header=_header("agent-gate-process", "PROCESS"),
        start="produce",
        permission="workflows.agent-gate.start",
        nodes={
            "produce": StepNode(
                id="produce",
                tool="produce@1",
                in_={},
                out={"recommendation": "state.recommendation"},
                next="sign-off",
            ),
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.recommendation",),
                deciders=(Decider(kind="agent", ref="review@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "DENIED": Ending(outcome="STOPPED", says="Denied."),
        },
        state={},
    )


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


async def _no_real_sleep(seconds: float) -> None:
    """Stub for `asyncio.sleep` in tests that exercise a TRANSIENT retry but
    aren't testing its backoff timing — keeps them fast."""


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


def test_code_step_attempt_record_carries_its_real_resolved_inputs():
    """§12.2: an attempt record's `inputs` is "inputs used", not an empty
    placeholder. Before this fix, every `AttemptRecord` in run.py was built
    with `inputs={}` regardless of what was actually resolved and dispatched
    — this covers the inline `CODE`-mechanism dispatch path (`_record_step_result`,
    shared by every STEP-attempt recording site), where the real resolved
    inputs were already computed to decide whether dispatch could even be
    attempted, then discarded rather than recorded."""
    records = StubRecordsAdapter()
    process = _process()
    _run(
        next_(
            process,
            "run-inputs-1",
            "root",
            _fresh_ctx(records=records),
            inputs={"question": "why did it fail"},
            host_inputs={},
        )
    )
    attempts = _run(
        records.get_attempts(
            "run-inputs-1",
            "root",
            "classify",
            platform_id="tenant-1",
            run_id="run-inputs-1",
        )
    )
    assert len(attempts) == 1
    assert attempts[0].inputs == {"question": "why did it fail"}


class _RaceOnceRecordsAdapter:
    """Wraps a `StubRecordsAdapter`, injecting a competing write for one
    chosen node the first time its attempts are read as empty.

    This is the race described in §12.2's write-once guard: two `next()`
    calls both replaying from the same durable position see zero existing
    attempts for a node, both compute the identical next `AttemptKey`, and
    one loses the race to record it. Here the "someone else" caller's write
    lands in the window between this call's `get_attempts` read and its own
    `record_attempt` write, so the real write-once guard in
    `StubRecordsAdapter.record_attempt` raises `DuplicateAttempt` on this
    call's own attempt — exactly the collision `_record_attempt` must
    swallow rather than let crash out of `next()`.
    """

    def __init__(self, inner: StubRecordsAdapter, *, node: str) -> None:
        self._inner = inner
        self._raced_node = node
        self._raced = False

    @property
    def identity(self):
        return self._inner.identity

    async def record_attempt(self, record, *, platform_id, run_id):
        await self._inner.record_attempt(record, platform_id=platform_id, run_id=run_id)

    async def get_attempts(self, run, scope, node, *, platform_id, run_id):
        attempts = await self._inner.get_attempts(
            run, scope, node, platform_id=platform_id, run_id=run_id
        )
        if not self._raced and node == self._raced_node and not attempts:
            self._raced = True
            phantom = AttemptRecord(
                key=AttemptKey(run=run, scope=scope, node=node, attempt=1),
                inputs={},
                output=None,
                control_results=[],
                verdict=None,
                performed_by="someone-else",
                started_at="2024-01-01T00:00:00Z",
                ended_at="2024-01-01T00:00:00Z",
            )
            self._inner._store[phantom.key] = phantom
        return attempts


def test_second_racing_caller_recording_the_same_attempt_is_not_a_crash():
    """§12.2: `record_attempt` MUST raise `DuplicateAttempt` on a second
    write to the same `AttemptKey`. Before this fix, nothing in run.py
    caught it, so two `next()` calls racing from the same durable replay
    position — both seeing zero existing attempts, both computing the same
    next `AttemptKey`, one losing the race to record it — crashed with an
    unhandled `DuplicateAttempt` instead of completing normally like any
    other resumed call reading work someone else already durably recorded.
    """
    inner = StubRecordsAdapter()
    racing_records = _RaceOnceRecordsAdapter(inner, node="classify")
    process = _process()
    answer = _run(
        next_(
            process,
            "run-dup-1",
            "root",
            _fresh_ctx(records=racing_records),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "COMPLETE"


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


def test_gate_agent_decider_permit_with_evidence_completes_via_report():
    """§7.6 end to end: an `agent` decider's `DECISION_STEP` hand-off is
    completed by `report()`, the way gates.py's own docstring says it must
    be — this was previously impossible: `check_agent_decision` existed
    but nothing ever called it (see the run record for this fix)."""
    process = _agent_gate_process()
    records = StubRecordsAdapter()
    registry = Registry([_produce_tool(), _review_tool()])

    producer_ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="agent:producer",
        platform_id="tenant-1",
    )
    first = _run(
        next_(
            process, "run-agent-gate-1", "root", producer_ctx, inputs={}, host_inputs={}
        )
    )
    assert first.kind is AnswerKind.TOOL_STEP
    second = _run(
        report(
            process,
            "run-agent-gate-1",
            "root",
            "produce",
            producer_ctx,
            inputs={},
            host_inputs={},
            output={"recommendation": "adopt the finding"},
        )
    )
    assert second.kind is AnswerKind.DECISION_STEP
    assert second.node_id == "sign-off"

    reviewer_ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="agent:reviewer",
        platform_id="tenant-1",
    )
    third = _run(
        report(
            process,
            "run-agent-gate-1",
            "root",
            "sign-off",
            reviewer_ctx,
            inputs={},
            host_inputs={},
            output={
                "verdict": "PERMIT",
                "rationale": "The recommendation is grounded in the finding.",
                "evidence": [
                    {"path": "state.recommendation", "claim": "grounded"},
                ],
            },
        )
    )
    assert third.kind is AnswerKind.ENDED
    assert third.ending == "COMPLETE"


def test_gate_agent_decider_is_refused_before_counting_when_tool_has_no_permission():
    """Mirrors the STEP-side fix: an `agent` decider whose Tool declares no
    `permission` must not have its vote counted — it becomes INDETERMINATE
    (the gate's own existing fallback for an undecided decider), not a
    silent PERMIT/DENY and not a crash."""
    process = _agent_gate_process()
    records = StubRecordsAdapter()
    registry = Registry([_produce_tool(), _review_tool(permission=None)])

    producer_ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="agent:producer",
        platform_id="tenant-1",
    )
    _run(
        next_(
            process, "run-agent-gate-2", "root", producer_ctx, inputs={}, host_inputs={}
        )
    )
    _run(
        report(
            process,
            "run-agent-gate-2",
            "root",
            "produce",
            producer_ctx,
            inputs={},
            host_inputs={},
            output={"recommendation": "adopt the finding"},
        )
    )

    reviewer_ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="agent:reviewer",
        platform_id="tenant-1",
    )
    answer = _run(
        report(
            process,
            "run-agent-gate-2",
            "root",
            "sign-off",
            reviewer_ctx,
            inputs={},
            host_inputs={},
            output={
                "verdict": "PERMIT",
                "rationale": "Looks fine.",
                "evidence": [{"path": "state.recommendation", "claim": "grounded"}],
            },
        )
    )
    assert answer.kind is AnswerKind.AWAITING_DECISION

    attempts = _run(
        records.get_attempts(
            "run-agent-gate-2",
            "root",
            "sign-off",
            platform_id="tenant-1",
            run_id="run-agent-gate-2",
        )
    )
    assert attempts[-1].verdict == Verdict.INDETERMINATE.value
    assert "permission" in (attempts[-1].output or {}).get("rationale", "")


def test_gate_agent_decider_cannot_decide_on_its_own_work():
    """§7.6, ANSI INCITS 359-2004: the same identity that produced a
    reviewed value cannot also be the one deciding on it — proven end to
    end via `report()`, not just against `check_agent_decision` in
    isolation (already covered in test_gates.py)."""
    process = _agent_gate_process()
    records = StubRecordsAdapter()
    registry = Registry([_produce_tool(), _review_tool()])

    same_identity_ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="agent:same-session",
        platform_id="tenant-1",
    )
    _run(
        next_(
            process,
            "run-agent-gate-3",
            "root",
            same_identity_ctx,
            inputs={},
            host_inputs={},
        )
    )
    _run(
        report(
            process,
            "run-agent-gate-3",
            "root",
            "produce",
            same_identity_ctx,
            inputs={},
            host_inputs={},
            output={"recommendation": "adopt the finding"},
        )
    )

    answer = _run(
        report(
            process,
            "run-agent-gate-3",
            "root",
            "sign-off",
            same_identity_ctx,
            inputs={},
            host_inputs={},
            output={
                "verdict": "PERMIT",
                "rationale": "Looks fine.",
                "evidence": [{"path": "state.recommendation", "claim": "grounded"}],
            },
        )
    )
    assert answer.kind is AnswerKind.AWAITING_DECISION

    attempts = _run(
        records.get_attempts(
            "run-agent-gate-3",
            "root",
            "sign-off",
            platform_id="tenant-1",
            run_id="run-agent-gate-3",
        )
    )
    assert attempts[-1].verdict == Verdict.INDETERMINATE.value
    assert "own work" in (attempts[-1].output or {}).get("rationale", "")


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


def test_note_into_an_append_channel_is_refused_cleanly_rather_than_crashing():
    """D27: `_state_with_note` recomputes and re-applies the gate's note on
    every replay pass that reaches a DECIDED resolution — safe only for
    REPLACE (idempotent under repeated identical writes), not APPEND (would
    silently accumulate the same note again on every replay). V9 already
    refuses this at validation time; this is the validator-bypass case,
    proving the OLD behaviour (an uncaught ReducerMismatch) is gone and
    the run ends cleanly instead."""
    from sulis_workflows.definition.model import StateChannel

    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="person", permission="approve.thing"),),
                note_into="state.notes",
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        },
        state={"notes": StateChannel(type="list<string>", reducer="APPEND")},
    )
    records = StubRecordsAdapter()
    ctx = _fresh_ctx(records=records)
    first = _run(
        next_(process, "run-9", "root", ctx, inputs={"question": "why"}, host_inputs={})
    )
    assert first.kind is AnswerKind.AWAITING_DECISION

    second = _run(
        decide(
            process,
            "run-9",
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
    assert second.ending == "FAILED"
    assert second.outcome == "FAILURE"
    assert "notes" in second.says
    assert "APPEND" in second.says


def test_note_into_captures_a_policy_deciders_own_rationale_on_deny():
    """D32: `note_into`'s write source is not person-specific — a `policy`
    (or `agent`) decider's own `rationale` is the same kind of provenance
    content as a `person`'s own `note` (§7.6's Provenance bullet: "the
    rationale or note", named side by side). Before this fix, a
    policy-decided DENY left `note_into`'s target channel untouched, since
    only a person's own attempt record ever carried a `note` key — a
    `policy`/`agent` decider's own reason for its verdict was silently
    dropped exactly like D24's original bug, just for two of the three
    decider kinds rather than all three."""
    from sulis_workflows.definition.model import StateChannel

    log_tool = Tool(
        header=_header("log-note", "TOOL"),
        output={},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:log_note"),
        effect="QUERY",
        # A default (rather than `required`) means an unwritten `state.note`
        # (still "", its declared default — §7.1: "the first present,
        # non-empty value is used", so an empty string never resolves)
        # dispatches with an empty note instead of refusing outright — the
        # distinction this test is about is the note's *content*, not
        # whether the step can dispatch at all.
        inputs={"note": InputSpec(type="string", default="")},
        permission="workflows.log-note.dispatch",
    )
    process = Process(
        header=_header("note-capture-process", "PROCESS"),
        start="sign-off",
        permission="workflows.note-capture-process.start",
        nodes={
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="policy", ref="sign-off-policy@1"),),
                note_into="state.note",
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(next="log-note"),
                },
            ),
            "log-note": StepNode(
                id="log-note",
                tool="log-note@1",
                in_={"note": "state.note"},
                out={},
                end="LOGGED",
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "LOGGED": Ending(outcome="SUCCESS", says="Logged."),
        },
        state={"note": StateChannel(type="string", reducer="REPLACE", default="")},
    )
    registry = Registry([log_tool])
    policy = StubPolicyAdapter(policy_denies={"sign-off-policy@1"})
    records = StubRecordsAdapter()
    ctx = EngineContext(
        policy=policy,
        code_tool=StubCodeToolAdapter(responses={"mod:log_note": {}}),
        records=records,
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-note-1", "root", ctx, inputs={}, host_inputs={}))
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "LOGGED"

    attempts = _run(
        records.get_attempts(
            "run-note-1",
            "root",
            "log-note",
            platform_id="tenant-1",
            run_id="run-note-1",
        )
    )
    assert len(attempts) == 1
    assert attempts[0].inputs == {"note": "stub-denied:sign-off-policy@1"}


def test_step_with_skill_mechanism_hands_off_as_tool_step_then_report_completes_it():
    agentic_tool = Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/classify"),
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
    assert first.instructions_ref == "skills/classify"
    assert first.controls == ()

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


def test_tool_step_hand_off_carries_instructions_ref_and_controls():
    """§12.1: `TOOL_STEP` carries "resolved inputs, instructions ref,
    controls" — previously only `resolved_inputs` reached the caller; the
    Tool's own mechanism `ref` (§4.3: "a skill document" for SKILL) and
    its declared `controls` were only reachable by the caller looking the
    Tool up itself."""
    skill_tool = Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(
            ControlRef(kind="profile", ref="verdict-shape@1"),
            ControlRef(kind="conventions", ref="output-present@1"),
        ),
        mechanism=Mechanism(kind="SKILL", ref="skills/classify-inquiry"),
        effect="QUERY",
        inputs={"question": InputSpec(type="string")},
        permission="workflows.classify.dispatch",
    )
    process = _process()
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([skill_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(
            process,
            "run-instructions-1",
            "root",
            ctx,
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.instructions_ref == "skills/classify-inquiry"
    assert answer.controls == (
        {"kind": "profile", "ref": "verdict-shape@1"},
        {"kind": "conventions", "ref": "output-present@1"},
    )


def test_decide_is_refused_when_the_person_decider_declares_no_permission():
    """§10.1: "...or accepts any decision, it asks the host's PolicyPort"
    — decide() previously recorded any verdict from any caller with no
    authorization check at all. Mirrors the STEP/GATE-agent fixes."""
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="person", permission=None),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    records = StubRecordsAdapter()
    ctx = _fresh_ctx(records=records)
    _run(
        next_(
            process,
            "run-decide-1",
            "root",
            ctx,
            inputs={"question": "why"},
            host_inputs={},
        )
    )

    answer = _run(
        decide(
            process,
            "run-decide-1",
            "root",
            "sign-off",
            _fresh_ctx(records=records),
            inputs={"question": "why"},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note=None,
            subject="user-42",
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_decide_is_refused_when_the_person_deciders_permission_is_denied():
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
    policy = StubPolicyAdapter(denies={"approve.thing"})
    _run(
        next_(
            process,
            "run-decide-2",
            "root",
            _fresh_ctx(records=records, policy=policy),
            inputs={"question": "why"},
            host_inputs={},
        )
    )

    answer = _run(
        decide(
            process,
            "run-decide-2",
            "root",
            "sign-off",
            _fresh_ctx(records=records, policy=policy),
            inputs={"question": "why"},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note=None,
            subject="user-42",
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_decide_uses_the_gates_own_permission_when_no_deciders_are_declared():
    """D13: "If `deciders` is absent, the gate is decided by a person
    holding the gate's permission" — proven by granting only the GATE's
    own permission, not any (non-existent) decider's."""
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(),
                permission="gate-level.approve",
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    records = StubRecordsAdapter()
    policy = StubPolicyAdapter()  # permits everything, including gate-level.approve
    _run(
        next_(
            process,
            "run-decide-3",
            "root",
            _fresh_ctx(records=records, policy=policy),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    answer = _run(
        decide(
            process,
            "run-decide-3",
            "root",
            "sign-off",
            _fresh_ctx(records=records, policy=policy),
            inputs={"question": "why"},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note=None,
            subject="user-42",
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "COMPLETE"


def test_decide_after_a_deny_loop_back_still_uses_the_person_deciders_permission():
    """WP-03a Fault 1: `decide()` used to compute which decider it was
    satisfying from `len(attempts)` — the gate's TOTAL attempt count
    across every past visit, not this visit's own. A person GATE with no
    gate-level `permission` and exactly one `person` decider, looped back
    on DENY: after the loop-back, the gate's store already holds one
    attempt (the first DENY), so the second `decide()` computed
    `decider_index = 1`, overshot `len(node.deciders) == 1`, and fell
    back to the (undeclared) gate-level permission — refusing FORBIDDEN
    a decision the person decider's own permission should have allowed.
    Same D20/D21/D22 visit-baseline bug class, in `decide()`."""
    draft_tool = Tool(
        header=_header("draft", "TOOL"),
        output={"text": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/draft"),
        effect="QUERY",
        permission="notes.note.draft",
    )
    process = Process(
        header=_header("resend-for-approval", "PROCESS"),
        start="draft",
        permission="workflows.resend-for-approval.start",
        nodes={
            "draft": StepNode(
                id="draft", tool="draft@1", in_={}, out={}, next="approve"
            ),
            "approve": GateNode(
                id="approve",
                kind="APPROVAL",
                asks="Approve this note?",
                reviewing=(),
                deciders=(Decider(kind="person", permission="notes.note.approve"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="draft",
                        loop=LoopSpec(budget=2, on_exhausted=RouteTarget(end="DENIED")),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Approved."),
            "DENIED": Ending(outcome="STOPPED", says="Denied too many times."),
        },
    )
    records = StubRecordsAdapter()
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([draft_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )

    answer = _run(
        next_(process, "run-decide-loop-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "draft"

    answer = _run(
        report(
            process,
            "run-decide-loop-1",
            "root",
            "draft",
            ctx,
            inputs={},
            host_inputs={},
            output={"text": "v1"},
        )
    )
    assert answer.kind is AnswerKind.AWAITING_DECISION
    assert answer.node_id == "approve"

    answer = _run(
        decide(
            process,
            "run-decide-loop-1",
            "root",
            "approve",
            ctx,
            inputs={},
            host_inputs={},
            verdict=Verdict.DENY,
            note="not yet",
            subject="reviewer-1",
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP, answer
    assert answer.node_id == "draft"

    answer = _run(
        report(
            process,
            "run-decide-loop-1",
            "root",
            "draft",
            ctx,
            inputs={},
            host_inputs={},
            output={"text": "v2"},
        )
    )
    assert answer.kind is AnswerKind.AWAITING_DECISION, answer
    assert answer.node_id == "approve"

    answer = _run(
        decide(
            process,
            "run-decide-loop-1",
            "root",
            "approve",
            ctx,
            inputs={},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note="looks good now",
            subject="reviewer-1",
        )
    )
    assert answer.kind is AnswerKind.ENDED, answer
    assert answer.ending == "COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_decide_after_a_policy_indeterminate_loop_uses_the_correct_decider_index():
    """WP-03a Fault 1, the general case: `approve`'s deciders are
    `[policy, person]`. Visit 1 the policy decider DENYs outright
    (decided at decider_index 0, one attempt) and loops back; visit 2 the
    same policy ref answers INDETERMINATE instead (decided at
    decider_index 1, two attempts, falling through to the person decider)
    — a resolution of a DIFFERENT length than visit 1's. `decide()` must
    still identify decider_index 1 (the person) correctly, proving the
    fix replays each visit's own resolution rather than just repeating a
    fixed offset."""

    class FlipPolicy:
        def __init__(self, verdicts):
            self._verdicts = list(verdicts)
            self._calls = 0

        async def authorize(self, permission, *, identity, platform_id, run_id):
            return PolicyDecision(verdict=Verdict.PERMIT)

        async def evaluate_policy(
            self, ref, *, reviewing, identity, platform_id, run_id
        ):
            verdict = self._verdicts[min(self._calls, len(self._verdicts) - 1)]
            self._calls += 1
            return PolicyDecision(verdict=verdict, rationale=f"call {self._calls}")

    draft_tool = Tool(
        header=_header("draft", "TOOL"),
        output={"text": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/draft"),
        effect="QUERY",
        permission="notes.note.draft",
    )
    process = Process(
        header=_header("resend-for-approval-2", "PROCESS"),
        start="draft",
        permission="workflows.resend-for-approval-2.start",
        nodes={
            "draft": StepNode(
                id="draft", tool="draft@1", in_={}, out={}, next="approve"
            ),
            "approve": GateNode(
                id="approve",
                kind="APPROVAL",
                asks="Approve this note?",
                reviewing=(),
                deciders=(
                    Decider(kind="policy", ref="auto-approve@1"),
                    Decider(kind="person", permission="notes.note.approve"),
                ),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="draft",
                        loop=LoopSpec(budget=2, on_exhausted=RouteTarget(end="DENIED")),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Approved."),
            "DENIED": Ending(outcome="STOPPED", says="Denied too many times."),
        },
    )
    records = StubRecordsAdapter()
    policy = FlipPolicy([Verdict.DENY, Verdict.INDETERMINATE])
    ctx = EngineContext(
        policy=policy,
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([draft_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )

    answer = _run(
        next_(process, "run-decide-loop-2", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    answer = _run(
        report(
            process,
            "run-decide-loop-2",
            "root",
            "draft",
            ctx,
            inputs={},
            host_inputs={},
            output={"text": "v1"},
        )
    )
    # policy DENYs outright -> loop back to draft, no person decision needed this visit.
    assert answer.kind is AnswerKind.TOOL_STEP, answer
    assert answer.node_id == "draft"

    answer = _run(
        report(
            process,
            "run-decide-loop-2",
            "root",
            "draft",
            ctx,
            inputs={},
            host_inputs={},
            output={"text": "v2"},
        )
    )
    # policy now answers INDETERMINATE -> falls through to the person decider.
    assert answer.kind is AnswerKind.AWAITING_DECISION, answer
    assert answer.node_id == "approve"

    answer = _run(
        decide(
            process,
            "run-decide-loop-2",
            "root",
            "approve",
            ctx,
            inputs={},
            host_inputs={},
            verdict=Verdict.PERMIT,
            note="ok",
            subject="reviewer-1",
        )
    )
    assert answer.kind is AnswerKind.ENDED, answer
    assert answer.ending == "COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_skill_mechanism_step_is_refused_before_hand_off_with_no_permission():
    """§10.1/D12: permission is checked before ANY dispatch — a `TOOL_STEP`
    hand-off is the dispatch for a `SKILL` Tool, so a Tool with no
    declared `permission` must never reach the caller as a hand-off, the
    same as a CODE Tool never reaches `code_tool.call()`."""
    agentic_tool = Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/classify"),
        effect="QUERY",
        inputs={"question": InputSpec(type="string")},
        permission=None,
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([agentic_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(
            _process(),
            "run-forbid-skill-1",
            "root",
            ctx,
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_skill_mechanism_step_is_refused_before_hand_off_when_permission_denied():
    agentic_tool = Tool(
        header=_header("classify", "TOOL"),
        output={"verdict": OutputSpec(type="enum[A, B]")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/classify"),
        effect="QUERY",
        inputs={"question": InputSpec(type="string")},
        permission="workflows.classify.dispatch",
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(denies={"workflows.classify.dispatch"}),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([agentic_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(
            _process(),
            "run-forbid-skill-2",
            "root",
            ctx,
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_transient_error_retries_then_succeeds(monkeypatch):
    # D31 makes a TRANSIENT retry sleep for real (`backoff_seconds`) before
    # redispatching; this test is about retry happening at all, not about
    # timing, so the backoff sleep itself is stubbed out to keep it fast.
    monkeypatch.setattr(
        "sulis_workflows.engine.run.asyncio.sleep",
        _no_real_sleep,
    )
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


def test_transient_retry_waits_with_exponential_backoff(monkeypatch):
    """spec §7.1/§15: `backoff_seconds` is "the starting delay before
    exponential backoff" for a TRANSIENT retry. Before this fix, nothing in
    `_advance_step` ever read `retry.backoff_seconds` (or the format
    default) at all — every retry redispatched back-to-back with no delay,
    silently ignoring a declared or defaulted backoff."""
    sleeps: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("sulis_workflows.engine.run.asyncio.sleep", _record_sleep)

    base_process = _process()
    nodes = dict(base_process.nodes)
    nodes["classify"] = StepNode(
        id="classify",
        tool="classify@1",
        in_={"question": "inputs.question"},
        out={"verdict": "state.verdict"},
        next="after-classify",
        on_error={"FLAKY": RouteTarget(end="FAILED_FLAKY")},
        retry=RetrySpec(max=3, backoff_seconds=1.0),
    )
    process = _process(nodes=nodes)

    call_count = {"n": 0}

    class FlakyTwiceThenOkAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise ToolTransientError("FLAKY")
            return {"verdict": "A"}

    ctx = _fresh_ctx(records=StubRecordsAdapter(), code_tool=FlakyTwiceThenOkAdapter())
    answer = _run(
        next_(
            process,
            "run-backoff-1",
            "root",
            ctx,
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.ending == "COMPLETE"
    assert call_count["n"] == 3
    # backoff_seconds=1.0: first retry waits 1.0s (2**0), second waits 2.0s (2**1).
    assert sleeps == [1.0, 2.0]


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


def test_hand_off_mutation_step_acquires_a_claim_so_a_second_caller_is_told_step_running():
    """D37: §12.3's claim/lease guard ("before a MUTATION or SIDE_EFFECT
    step runs, the engine writes an in-progress claim") is the
    dispatch-time at-most-once protection this format has — and a
    `TOOL_STEP` hand-off IS this step's own dispatch, the same reasoning
    §10.1/D12's permission check already applies to hand-offs. Before this
    fix, `ctx.claims.acquire` was only ever called on the inline `CODE`
    dispatch path below — a hand-off `SKILL` Tool (the case a real-world
    side effect performed by an external agent most needs at-most-once
    protection for) acquired no claim at all, so a second caller racing in
    during the hand-off got a fresh `TOOL_STEP` instead of `STEP_RUNNING`.
    """
    mutating_tool = Tool(
        header=_header("send", "TOOL"),
        output={"sent": OutputSpec(type="boolean")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/send"),
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
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=claims,
        registry=registry,
        identity="user:iain",
        platform_id="tenant-1",
    )

    first = _run(
        next_(process, "run-hand-off-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert first.kind is AnswerKind.TOOL_STEP

    second = _run(
        next_(process, "run-hand-off-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert second.kind is AnswerKind.STEP_RUNNING


def test_route_loop_budget_is_enforced_across_revisits():

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


def test_route_loop_with_no_own_budget_uses_the_process_declared_default():
    """§7.3/§15: a loop's own `budget` beats the process's `defaults.loop_budget`,
    which beats the format default (10, `definition/defaults.py`). Before this
    fix, `_advance_route` always passed `process_default_budget=None` to
    `check_loop_budget`, so a loop with no `budget` of its own silently fell
    straight through to the format default even when the process declared its
    own — the same disagreement `explain` (`cli.py`) never had, since it
    already implements the full 3-tier fallback."""

    process = Process(
        header=_header("loopy-process", "PROCESS"),
        start="loopy",
        permission="workflows.loopy.start",
        defaults=ProcessDefaults(loop_budget=2),
        nodes={
            "loopy": RouteNode(
                id="loopy",
                when=(
                    RouteOption(
                        if_="true",
                        next="loopy",
                        loop=LoopSpec(on_exhausted=RouteTarget(end="LOOP_DONE")),
                    ),
                ),
            ),
        },
        endings={"LOOP_DONE": Ending(outcome="SUCCESS", says="Loop finished.")},
    )
    records = StubRecordsAdapter()
    ctx = _fresh_ctx(records=records)
    answer = _run(next_(process, "run-loop-3", "root", ctx, inputs={}, host_inputs={}))
    assert answer.ending == "LOOP_DONE"
    attempts = _run(
        records.get_attempts(
            "run-loop-3", "root", "loopy", platform_id="tenant-1", run_id="run-loop-3"
        )
    )
    # The process's own defaults.loop_budget=2 permits exactly 2 loop-backs
    # (3 attempts total). Before the fix, the format default (10) applied
    # instead, so this would have kept looping to 11 attempts.
    assert len(attempts) == 3


def test_step_revisited_via_a_loop_gets_a_fresh_dispatch_each_time():
    # A STEP looped back to by a ROUTE must be re-dispatched each visit,
    # not resolved from a stale prior-visit record (the same class of bug
    # the ROUTE self-loop test above exists to catch, on the STEP side).

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


def test_multi_step_loop_body_spanning_separate_report_calls_advances_correctly():
    """D20: pressure-testing the real grounded-inquiry process (spec Appendix
    A) against the engine for the first time found this — a loop body with
    TWO SKILL (hand-off) steps got stuck asking for the first one forever
    after exactly one cycle, never reaching the second again and never
    exhausting the loop budget, because replay always jumped a node's own
    baseline straight to however many attempts now existed for it in total,
    which is only correct when nothing ELSE in the loop body has already
    recorded a later revisit's own attempts first. The existing loop tests
    above never caught this because their loop bodies are either a single
    node, or CODE-mechanism (dispatched synchronously, so the whole loop
    finishes inside one next_() call — no cross-call hand-off ever needed
    mid-loop). This is the first real one."""

    step_a_tool = Tool(
        header=_header("step-a", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/a"),
        effect="QUERY",
        permission="workflows.step-a.dispatch",
    )
    step_b_tool = Tool(
        header=_header("step-b", "TOOL"),
        output={"verdict": OutputSpec(type="enum[GO, STOP]")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/b"),
        effect="QUERY",
        permission="workflows.step-b.dispatch",
    )
    process = Process(
        header=_header("two-step-loop", "PROCESS"),
        start="a",
        permission="workflows.two-step-loop.start",
        nodes={
            "a": StepNode(id="a", tool="step-a@1", in_={}, out={}, next="b"),
            "b": StepNode(
                id="b",
                tool="step-b@1",
                in_={},
                out={"verdict": "state.verdict"},
                next="check",
            ),
            "check": RouteNode(
                id="check",
                when=(
                    RouteOption(
                        if_='state.verdict == "GO"',
                        next="a",
                        loop=LoopSpec(budget=2, on_exhausted=RouteTarget(end="DONE")),
                    ),
                ),
                otherwise=RouteTarget(end="DONE"),
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([step_a_tool, step_b_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )

    answer = _run(next_(process, "run-loop-3", "root", ctx, inputs={}, host_inputs={}))
    a_dispatches = 0
    b_dispatches = 0
    for _ in range(10):
        assert answer.kind is not AnswerKind.ENDED, "never reached DONE"
        if answer.node_id == "a":
            a_dispatches += 1
            answer = _run(
                report(
                    process,
                    "run-loop-3",
                    "root",
                    "a",
                    ctx,
                    inputs={},
                    host_inputs={},
                    output={"x": "ok"},
                )
            )
        elif answer.node_id == "b":
            b_dispatches += 1
            answer = _run(
                report(
                    process,
                    "run-loop-3",
                    "root",
                    "b",
                    ctx,
                    inputs={},
                    host_inputs={},
                    output={"verdict": "GO"},
                )
            )
        else:
            raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")
        if answer.kind is AnswerKind.ENDED:
            break
    assert answer.ending == "DONE"
    # budget=2 allows 2 loop-backs, so "a" and "b" are each freshly asked 3
    # times (the 3rd "b" answer is the one whose GO verdict the budget
    # check finds already exhausted, ending DONE without ever asking "a" a
    # 4th time) -- the bug this test originally guarded against asked for
    # "a" a 4th, 5th, 6th... time and never asked for "b" again at all; a
    # second, related bug found later (`_advance_route`'s own replay
    # branch reusing a stale, already-superseded route decision instead of
    # the earliest one this walk had not yet consumed) skipped asking "b"
    # a 3rd time at all once the loop had already been taken twice, which
    # this assertion now also guards against.
    assert a_dispatches == 3
    assert b_dispatches == 3


def test_gate_deny_loop_budget_is_enforced_across_askings():
    # spec S7.6's own worked example loops on DENY: DENY: { next: recommend, loop: { budget: N } }.

    process = Process(
        header=_header("gate-loop-process", "PROCESS"),
        start="sign-off",
        permission="workflows.gate-loop.start",
        nodes={
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="always-deny@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="sign-off",
                        loop=LoopSpec(
                            budget=2, on_exhausted=RouteTarget(end="GAVE_UP")
                        ),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(
                outcome="STOPPED", says="Gave up after too many denials."
            ),
        },
    )
    policy = StubPolicyAdapter(policy_denies={"always-deny@1"})
    ctx = EngineContext(
        policy=policy,
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-gate-loop-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.ending == "GAVE_UP"
    assert answer.outcome == "STOPPED"


def test_gate_deny_loop_with_no_own_budget_uses_the_process_declared_default():
    """Same disagreement as the ROUTE case, for a GATE's own DENY loop-back:
    before the fix, `_advance_gate` always passed `process_default_budget=None`
    to `check_loop_budget`, so `defaults.loop_budget` was silently ignored."""

    process = Process(
        header=_header("gate-loop-process", "PROCESS"),
        start="sign-off",
        permission="workflows.gate-loop.start",
        defaults=ProcessDefaults(loop_budget=2),
        nodes={
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="always-deny@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="sign-off",
                        loop=LoopSpec(on_exhausted=RouteTarget(end="GAVE_UP")),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(
                outcome="STOPPED", says="Gave up after too many denials."
            ),
        },
    )
    policy = StubPolicyAdapter(policy_denies={"always-deny@1"})
    records = StubRecordsAdapter()
    ctx = EngineContext(
        policy=policy,
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-gate-loop-2", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.ending == "GAVE_UP"
    attempts = _run(
        records.get_attempts(
            "run-gate-loop-2",
            "root",
            "sign-off",
            platform_id="tenant-1",
            run_id="run-gate-loop-2",
        )
    )
    # defaults.loop_budget=2 permits exactly 2 loop-backs (3 attempts total).
    # Before the fix, the format default (10) applied instead.
    assert len(attempts) == 3


def test_gate_loop_counts_failures_only_counts_deny_takes_toward_the_budget():
    """D33: §7.3/§15's `counts: FAILURES` ("only when taken because a check
    failed") is unambiguous for a GATE — `DECIDED` only ever carries PERMIT
    or DENY, and DENY is ADR-028's own negative outcome. Before this fix,
    `loop.counts` was accepted, parsed, and never read anywhere: every take
    counted toward the budget regardless of verdict, exactly `PASSES`
    semantics, whatever `counts` actually said.

    Both PERMIT and DENY loop back to the same gate here (unusual, but
    structurally valid) sharing one `LoopSpec` with `budget: 2,
    counts: FAILURES` — proving PERMIT-driven takes never count (however
    many happen) and only the 3rd DENY-driven take exhausts the budget."""
    shared_loop = LoopSpec(
        budget=2, counts="FAILURES", on_exhausted=RouteTarget(end="GAVE_UP")
    )
    process = Process(
        header=_header("gate-loop-failures-process", "PROCESS"),
        start="check",
        permission="workflows.gate-loop-failures.start",
        nodes={
            "check": GateNode(
                id="check",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="scripted@1"),),
                on={
                    "PERMIT": RouteTarget(next="check", loop=shared_loop),
                    "DENY": RouteTarget(next="check", loop=shared_loop),
                },
            ),
        },
        endings={
            "GAVE_UP": Ending(
                outcome="STOPPED", says="Gave up after too many denials."
            ),
        },
    )

    verdicts = [
        Verdict.PERMIT,
        Verdict.PERMIT,
        Verdict.DENY,
        Verdict.PERMIT,
        Verdict.DENY,
        Verdict.PERMIT,
        Verdict.DENY,
    ]
    call_count = {"n": 0}

    class ScriptedVerdictPolicyAdapter:
        def __init__(self):
            self.identity = StubPolicyAdapter().identity

        async def authorize(self, permission, *, identity, platform_id, run_id):
            return PolicyDecision(verdict=Verdict.PERMIT)

        async def evaluate_policy(
            self, ref, *, reviewing, identity, platform_id, run_id
        ):
            verdict = verdicts[call_count["n"]]
            call_count["n"] += 1
            return PolicyDecision(
                verdict=verdict, rationale=f"scripted:{verdict.value}"
            )

    ctx = EngineContext(
        policy=ScriptedVerdictPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(
            process,
            "run-gate-loop-failures-1",
            "root",
            ctx,
            inputs={},
            host_inputs={},
        )
    )
    assert answer.ending == "GAVE_UP"
    assert answer.outcome == "STOPPED"
    # 2 PERMITs (never counted) + 3 DENYs (the 3rd exhausts budget=2).
    assert call_count["n"] == 7


def test_route_loop_counts_failures_is_refused_cleanly_rather_than_misapplied():
    """D33: the validator-bypass case for V8's `counts: FAILURES` refusal —
    a ROUTE's own `when` branch has no engine-visible "because a check
    failed" signal, unlike a GATE's DENY verdict, so this is refused rather
    than silently treated as PASSES (or guessed at some other way)."""
    process = _process(
        nodes={
            **_process().nodes,
            "after-classify": RouteNode(
                id="after-classify",
                when=(
                    RouteOption(
                        if_='state.verdict == "A"',
                        next="classify",
                        loop=LoopSpec(budget=3, counts="FAILURES"),
                    ),
                    RouteOption(if_='state.verdict == "B"', end="DROPPED"),
                ),
            ),
        }
    )
    answer = _run(
        next_(
            process,
            "run-route-loop-failures-1",
            "root",
            _fresh_ctx(),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "FAILURES" in answer.says
    assert "after-classify" in answer.says


def test_route_invalidates_is_refused_cleanly_rather_than_silently_ignored():
    """D38: `invalidates` (spec §7.3) is accepted by the schema and model
    but never read anywhere the engine resolves state — nothing marks a
    channel invalid, and nothing checks for one. Refused rather than
    silently doing nothing, the same "refuse rather than guess" precedent
    D26/D27/D34 already set. This is the validator-bypass case; V18 is the
    validation-time half."""
    process = _process(
        nodes={
            **_process().nodes,
            "after-classify": RouteNode(
                id="after-classify",
                when=(
                    RouteOption(
                        if_='state.verdict == "A"',
                        end="DROPPED",
                        invalidates=("classify",),
                    ),
                    RouteOption(if_='state.verdict == "B"', end="DROPPED"),
                ),
            ),
        }
    )
    answer = _run(
        next_(
            process,
            "run-route-invalidates-1",
            "root",
            _fresh_ctx(),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "invalidates" in answer.says
    assert "after-classify" in answer.says


def test_route_replay_branch_carries_invalidates_so_the_refusal_is_not_silently_lost_on_a_later_call():
    """D38's own prerequisite fix: `_advance_route`'s replay branch (taken
    when a later call finds this node's decision already durably
    recorded, rather than evaluating it fresh) reconstructed `target`
    without `invalidates` before this fix — "correct once, silently
    dropped on replay", the same shape D19/D27 already found and fixed
    elsewhere in this file. Proven directly: the first `next_()` call
    resolves `after-classify` fresh and refuses, but only after durably
    recording the decision first (the existing refusal-after-recording
    order every other `_advance_route`/`_advance_gate` refusal already
    uses); a second `next_()` call against the SAME run replays that exact
    decision from the durable record rather than re-evaluating it — before
    the prerequisite fix, the replayed target silently dropped
    `invalidates` and let the run continue past the refusal instead of
    refusing a second time."""
    process = _process(
        nodes={
            **_process().nodes,
            "after-classify": RouteNode(
                id="after-classify",
                when=(
                    RouteOption(
                        if_='state.verdict == "A"',
                        end="DROPPED",
                        invalidates=("classify",),
                    ),
                    RouteOption(if_='state.verdict == "B"', end="DROPPED"),
                ),
            ),
        }
    )
    records = StubRecordsAdapter()
    for _ in range(2):
        answer = _run(
            next_(
                process,
                "run-route-invalidates-replay-1",
                "root",
                _fresh_ctx(records=records),
                inputs={"question": "why"},
                host_inputs={},
            )
        )
        assert answer.kind is AnswerKind.ENDED
        assert answer.ending == "FAILED"
        assert answer.outcome == "FAILURE"
        assert "invalidates" in answer.says
        assert "after-classify" in answer.says


def test_gate_invalidates_is_refused_cleanly_rather_than_silently_ignored():
    """D38: same refusal as the ROUTE case above — see that test's own
    docstring. `_advance_gate`'s `on{}` path reads the static model
    directly every call (no replay-branch bug there), so one call is
    enough to prove the refusal."""
    process = _process(
        nodes={
            **_process().nodes,
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=("state.verdict",),
                deciders=(Decider(kind="policy", ref="sign-off-policy@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE", invalidates=("classify",)),
                    "DENY": RouteTarget(end="DENIED"),
                },
            ),
        }
    )
    answer = _run(
        next_(
            process,
            "run-gate-invalidates-1",
            "root",
            _fresh_ctx(),
            inputs={"question": "why"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "invalidates" in answer.says
    assert "sign-off" in answer.says


def test_gate_loop_body_spanning_separate_report_calls_asks_the_decider_once_per_resolution():
    """D22: the D20/D21 bug class, found a third time — this time in
    `_advance_gate`. `test_gate_deny_loop_budget_is_enforced_across_askings`
    above loops the gate directly back to itself with no hand-off in
    between, so its own policy decider resolves the whole loop inside one
    `next_()` call and never touches the multi-call replay path this bug
    lives in. Here the gate's own DENY route loops back through TWO
    SKILL hand-offs (`work-a`, `work-b`) before reaching the gate again —
    the same shape as D20/D21's own STEP/ROUTE loop bodies, just for a
    GATE. Before the fix, once budget-2's worth of loop-backs had
    accumulated, a later replay call fed BOTH already-decided
    resolutions' attempts into `resolve_gate` at once, corrupting the
    loop-budget count and the durable record (5 `sign-off` attempts
    recorded for what should have been exactly 3 resolutions, one of them
    landing out of order relative to `work-b`'s own report)."""

    work_a_tool = Tool(
        header=_header("work-a", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/a"),
        effect="QUERY",
        permission="workflows.work-a.dispatch",
    )
    work_b_tool = Tool(
        header=_header("work-b", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/b"),
        effect="QUERY",
        permission="workflows.work-b.dispatch",
    )
    process = Process(
        header=_header("gate-loop-two-handoffs", "PROCESS"),
        start="work-a",
        permission="workflows.gate-loop-two-handoffs.start",
        nodes={
            "work-a": StepNode(
                id="work-a", tool="work-a@1", in_={}, out={}, next="work-b"
            ),
            "work-b": StepNode(
                id="work-b", tool="work-b@1", in_={}, out={}, next="sign-off"
            ),
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="always-deny@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="work-a",
                        loop=LoopSpec(
                            budget=2, on_exhausted=RouteTarget(end="GAVE_UP")
                        ),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(outcome="SUCCESS", says="Gave up."),
        },
    )
    records = StubRecordsAdapter()
    ctx = EngineContext(
        policy=StubPolicyAdapter(policy_denies={"always-deny@1"}),
        code_tool=StubCodeToolAdapter(),
        records=records,
        claims=StubClaimsAdapter(),
        registry=Registry([work_a_tool, work_b_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )

    answer = _run(
        next_(process, "run-gate-loop-2", "root", ctx, inputs={}, host_inputs={})
    )
    a_dispatches = 0
    b_dispatches = 0
    for _ in range(20):
        assert answer.kind is not AnswerKind.ENDED, "never reached an ending"
        if answer.node_id == "work-a":
            a_dispatches += 1
            answer = _run(
                report(
                    process,
                    "run-gate-loop-2",
                    "root",
                    "work-a",
                    ctx,
                    inputs={},
                    host_inputs={},
                    output={"x": "ok"},
                )
            )
        elif answer.node_id == "work-b":
            b_dispatches += 1
            answer = _run(
                report(
                    process,
                    "run-gate-loop-2",
                    "root",
                    "work-b",
                    ctx,
                    inputs={},
                    host_inputs={},
                    output={"x": "ok"},
                )
            )
        else:
            raise AssertionError(f"unexpected hand-off: {answer.node_id!r}")
        if answer.kind is AnswerKind.ENDED:
            break
    assert answer.ending == "GAVE_UP"
    assert answer.outcome == "SUCCESS"
    # budget=2 permits 2 loop-backs -> exactly 3 sign-off resolutions
    # (asked, denied, asked, denied, asked, exhausted) -> work-a/work-b
    # each dispatched exactly 3 times, matching the 3 resolutions, not 5.
    assert a_dispatches == 3
    assert b_dispatches == 3
    sign_off_attempts = _run(
        records.get_attempts(
            "run-gate-loop-2",
            "root",
            "sign-off",
            platform_id="tenant-1",
            run_id="run-gate-loop-2",
        )
    )
    assert [rec.verdict for rec in sign_off_attempts] == ["DENY", "DENY", "DENY"]


def test_gate_loop_body_spanning_separate_report_calls_uses_each_resolutions_own_verdict():
    """D22, the sharper failure mode the count-based test above cannot show
    on its own: before the fix, merging two resolutions' attempts into one
    `resolve_gate` call used only the FIRST decider's verdict and silently
    discarded the rest — if the first happened to be DENY and the second
    (the real, later verdict) was PERMIT, the run would never see the
    PERMIT at all. Same two-hand-off loop shape as above, but the policy
    decider answers DENY once, then PERMIT."""

    class FlipPolicy:
        def __init__(self, verdicts):
            self._verdicts = list(verdicts)
            self._calls = 0

        async def authorize(self, permission, *, identity, platform_id, run_id):
            return PolicyDecision(verdict=Verdict.PERMIT)

        async def evaluate_policy(
            self, ref, *, reviewing, identity, platform_id, run_id
        ):
            verdict = self._verdicts[min(self._calls, len(self._verdicts) - 1)]
            self._calls += 1
            return PolicyDecision(verdict=verdict, rationale=f"call {self._calls}")

    work_a_tool = Tool(
        header=_header("work-a", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/a"),
        effect="QUERY",
        permission="workflows.work-a.dispatch",
    )
    work_b_tool = Tool(
        header=_header("work-b", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/b"),
        effect="QUERY",
        permission="workflows.work-b.dispatch",
    )
    process = Process(
        header=_header("gate-loop-two-handoffs-flip", "PROCESS"),
        start="work-a",
        permission="workflows.gate-loop-two-handoffs-flip.start",
        nodes={
            "work-a": StepNode(
                id="work-a", tool="work-a@1", in_={}, out={}, next="work-b"
            ),
            "work-b": StepNode(
                id="work-b", tool="work-b@1", in_={}, out={}, next="sign-off"
            ),
            "sign-off": GateNode(
                id="sign-off",
                kind="APPROVAL",
                asks="Can this proceed?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="flip@1"),),
                on={
                    "PERMIT": RouteTarget(end="COMPLETE"),
                    "DENY": RouteTarget(
                        next="work-a",
                        loop=LoopSpec(
                            budget=5, on_exhausted=RouteTarget(end="GAVE_UP")
                        ),
                    ),
                },
            ),
        },
        endings={
            "COMPLETE": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(outcome="SUCCESS", says="Gave up."),
        },
    )
    ctx = EngineContext(
        policy=FlipPolicy([Verdict.DENY, Verdict.PERMIT]),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([work_a_tool, work_b_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )

    answer = _run(
        next_(process, "run-gate-loop-3", "root", ctx, inputs={}, host_inputs={})
    )
    for _ in range(20):
        if answer.kind is AnswerKind.ENDED:
            break
        answer = _run(
            report(
                process,
                "run-gate-loop-3",
                "root",
                answer.node_id,
                ctx,
                inputs={},
                host_inputs={},
                output={"x": "ok"},
            )
        )
    assert answer.ending == "COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_input_gate_is_refused_cleanly_rather_than_misrouted():
    """WP-03a Fault 2: `kind: INPUT` gates are refused at validation time
    (V9), but the validator is advisory — nothing stops a Process built
    directly (as every test here does) or loaded without going through
    `sulis-workflows validate` from reaching the engine with one. Before
    this fix, `_advance_gate` never read `node.kind` at all: a `policy`
    decider's PERMIT/DENY answer was evaluated as if this were an
    APPROVAL gate, found no matching route in `on` (an INPUT gate only
    ever declares `ANSWERED`), and raised the genuinely confusing "no
    route declared for verdict 'PERMIT'" — naming a verdict the gate's
    own author never wrote anywhere. The engine now recognises `kind:
    INPUT` itself and refuses with a clear, correctly-worded reason
    instead, the same defence-in-depth PARALLEL/JOIN/FOR_EACH already
    have against a validator bypass."""

    process = Process(
        header=_header("input-gate-process", "PROCESS"),
        start="ask",
        permission="workflows.input-gate.start",
        nodes={
            "ask": GateNode(
                id="ask",
                kind="INPUT",
                asks="What is the target date?",
                reviewing=(),
                deciders=(Decider(kind="policy", ref="always-permit@1"),),
                answer_type="string",
                answer_into="state.target_date",
                on={"ANSWERED": RouteTarget(end="COMPLETE")},
            ),
        },
        endings={"COMPLETE": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-input-gate-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "INPUT" in answer.says
    assert "no route declared for verdict" not in answer.says


def test_external_mechanism_step_is_refused_cleanly_rather_than_misrouted_as_a_skill():
    """D34: spec §4.3/§12.1 — `EXTERNAL` is meant to be run BY THE ENGINE
    (through a host adapter), the same side of the split as `CODE`. Before
    this fix, `_advance_step`'s generic `!= "CODE"` branch treated it
    exactly like a `SKILL` Tool, silently handing it off as a `TOOL_STEP`
    the caller's agent session could never actually perform. V17 already
    refuses this at validation time; this is the validator-bypass case."""
    external_tool = Tool(
        header=_header("notify-external", "TOOL"),
        output={"value": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="EXTERNAL", ref="adapter:notify"),
        effect="SIDE_EFFECT",
        inputs={},
        permission="workflows.notify-external.dispatch",
    )
    process = Process(
        header=_header("external-process", "PROCESS"),
        start="notify",
        permission="workflows.external-process.start",
        nodes={
            "notify": StepNode(
                id="notify", tool="notify-external@1", in_={}, out={}, end="DONE"
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([external_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-external-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "EXTERNAL" in answer.says
    assert answer.says != "Waiting on notify-external@1 to run."


def test_tool_composite_mechanism_step_is_refused_cleanly_rather_than_misrouted():
    """D34: `TOOL` (composite — child Tools run in order over shared
    values, spec §4.3) is also meant to be run BY THE ENGINE, but has no
    `ref` at all (only `composes`). Before this fix, the same generic
    hand-off branch produced a `TOOL_STEP` answer with `instructions_ref`
    silently `None` and every one of `composes`'s children dropped on the
    floor — refused instead, the validator-bypass case for V17."""
    from sulis_workflows.definition.model import ComposeItem

    composite_tool = Tool(
        header=_header("composite-echo", "TOOL"),
        output={"value": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(
            kind="TOOL",
            composes=(
                ComposeItem(tool="echo@1", inputs={"value": "inputs.value"}, output={}),
            ),
        ),
        effect="QUERY",
        inputs={},
        permission="workflows.composite-echo.dispatch",
    )
    process = Process(
        header=_header("composite-process", "PROCESS"),
        start="run-composite",
        permission="workflows.composite-process.start",
        nodes={
            "run-composite": StepNode(
                id="run-composite",
                tool="composite-echo@1",
                in_={},
                out={},
                end="DONE",
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([composite_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-composite-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"
    assert "TOOL" in answer.says


def test_control_fail_repair_gives_one_more_attempt_before_then():
    from sulis_workflows.definition.model import ControlFail, ControlRef, Profile

    tool = Tool(
        header=_header("draft", "TOOL"),
        output={"insight": OutputSpec(type="profile:insight@1")},
        controls=(ControlRef(kind="profile", ref="insight@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:draft"),
        effect="QUERY",
        permission="workflows.draft.dispatch",
    )
    process = Process(
        header=_header("repair-process", "PROCESS"),
        start="draft",
        permission="workflows.repair.start",
        nodes={
            "draft": StepNode(
                id="draft",
                tool="draft@1",
                in_={},
                out={"insight": "state.insight"},
                next="done",
                on_control_fail=ControlFail(repair=1, then=RouteTarget(end="GAVE_UP")),
            ),
        },
        endings={
            "done": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(outcome="FAILURE", says="Could not fix it."),
        },
    )
    profile = Profile(
        header=_header("insight", "PROFILE"),
        schema={
            "type": "object",
            "required": ["id", "claim"],
            "properties": {"id": {"type": "string"}, "claim": {"type": "string"}},
            "additionalProperties": False,
        },
    )

    call_count = {"n": 0}

    class RepairAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            # Always fails the profile control (missing "claim").
            return {"insight": {"id": f"i{call_count['n']}"}}

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=RepairAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tool, profile]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-repair-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.ending == "GAVE_UP"
    # repair=1 -> the original attempt plus exactly one repair attempt, then give up.
    assert call_count["n"] == 2


def test_control_fail_repair_receives_the_failures_as_input():
    from sulis_workflows.definition.model import ControlFail, ControlRef, Profile

    tool = Tool(
        header=_header("draft", "TOOL"),
        output={"insight": OutputSpec(type="profile:insight@1")},
        controls=(ControlRef(kind="profile", ref="insight@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:draft"),
        effect="QUERY",
        permission="workflows.draft.dispatch",
        inputs={"prior_findings": InputSpec(type="any", required=False)},
    )
    process = Process(
        header=_header("repair-process", "PROCESS"),
        start="draft",
        permission="workflows.repair.start",
        nodes={
            "draft": StepNode(
                id="draft",
                tool="draft@1",
                in_={"prior_findings": "steps.draft.controls.insight.findings"},
                out={"insight": "state.insight"},
                next="done",
                on_control_fail=ControlFail(repair=1, then=RouteTarget(end="GAVE_UP")),
            ),
        },
        endings={
            "done": Ending(outcome="SUCCESS", says="Done."),
            "GAVE_UP": Ending(outcome="FAILURE", says="Could not fix it."),
        },
    )
    profile = Profile(
        header=_header("insight", "PROFILE"),
        schema={
            "type": "object",
            "required": ["id", "claim"],
            "properties": {"id": {"type": "string"}, "claim": {"type": "string"}},
            "additionalProperties": False,
        },
    )

    received_inputs = []

    class RepairAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            received_inputs.append(inputs)
            if len(received_inputs) == 1:
                return {"insight": {"id": "i1"}}  # missing "claim" -> fails the control
            return {"insight": {"id": "i2", "claim": "now grounded"}}  # fixed on repair

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=RepairAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tool, profile]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(process, "run-repair-2", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.ending == "done"
    assert len(received_inputs) == 2
    assert "prior_findings" not in received_inputs[0]  # nothing to report yet
    assert received_inputs[1][
        "prior_findings"
    ]  # the first attempt's findings, non-empty


def test_skip_a_trivial_step_under_advisory_policy_reaches_the_end():

    tool = Tool(
        header=_header("optional-check", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:optional"),
        effect="QUERY",
        permission="workflows.optional.dispatch",
    )
    process = Process(
        header=_header("guided-process", "PROCESS"),
        start="optional",
        permission="workflows.guided.start",
        skip_policy="ADVISORY",
        nodes={
            "optional": StepNode(
                id="optional",
                tool="optional-check@1",
                in_={},
                out={},
                criticality="TRIVIAL",
                skip_permission="workflows.optional.skip",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    call_count = {"n": 0}

    class NeverCalledAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            return {"x": "should not happen"}

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=NeverCalledAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        skip(
            process,
            "run-skip-1",
            "root",
            "optional",
            ctx,
            inputs={},
            host_inputs={},
            reason="not needed for this brief",
            subject="user-42",
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "done"
    assert call_count["n"] == 0  # the Tool was never dispatched


def test_skip_is_refused_without_permission_being_granted():

    process = Process(
        header=_header("guided-process-2", "PROCESS"),
        start="optional",
        permission="workflows.guided.start",
        skip_policy="ADVISORY",
        nodes={
            "optional": StepNode(
                id="optional",
                tool="optional-check@1",
                in_={},
                out={},
                criticality="TRIVIAL",
                skip_permission="workflows.optional.skip",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    policy = StubPolicyAdapter(denies={"workflows.optional.skip"})
    ctx = EngineContext(
        policy=policy,
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        skip(
            process,
            "run-skip-2",
            "root",
            "optional",
            ctx,
            inputs={},
            host_inputs={},
            reason="not needed",
            subject="user-42",
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FORBIDDEN"


def test_skip_a_standard_step_is_refused_even_under_advisory():

    process = Process(
        header=_header("guided-process-3", "PROCESS"),
        start="required",
        permission="workflows.guided.start",
        skip_policy="ADVISORY",
        nodes={
            "required": StepNode(
                id="required",
                tool="optional-check@1",
                in_={},
                out={},
                criticality="STANDARD",
                skip_permission="workflows.required.skip",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    with pytest.raises(EngineRefusal):
        _run(
            skip(
                process,
                "run-skip-3",
                "root",
                "required",
                ctx,
                inputs={},
                host_inputs={},
                reason="let's try anyway",
                subject="user-42",
            )
        )


def test_skip_is_refused_when_the_process_is_strict_not_advisory():

    process = Process(
        header=_header("strict-process", "PROCESS"),
        start="optional",
        permission="workflows.strict.start",
        skip_policy="STRICT",
        nodes={
            "optional": StepNode(
                id="optional",
                tool="optional-check@1",
                in_={},
                out={},
                criticality="TRIVIAL",
                skip_permission="workflows.optional.skip",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    with pytest.raises(EngineRefusal):
        _run(
            skip(
                process,
                "run-skip-4",
                "root",
                "optional",
                ctx,
                inputs={},
                host_inputs={},
                reason="try skipping anyway",
                subject="user-42",
            )
        )


def test_skip_is_refused_when_the_step_declares_no_skip_permission():

    process = Process(
        header=_header("guided-process-4", "PROCESS"),
        start="optional",
        permission="workflows.guided.start",
        skip_policy="ADVISORY",
        nodes={
            "optional": StepNode(
                id="optional",
                tool="optional-check@1",
                in_={},
                out={},
                criticality="TRIVIAL",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    with pytest.raises(EngineRefusal):
        _run(
            skip(
                process,
                "run-skip-5",
                "root",
                "optional",
                ctx,
                inputs={},
                host_inputs={},
                reason="try anyway",
                subject="user-42",
            )
        )


def test_advisory_process_that_is_never_skipped_runs_normally():
    process = Process(
        header=_header("guided-process-5", "PROCESS"),
        start="optional",
        permission="workflows.guided.start",
        skip_policy="ADVISORY",
        nodes={
            "optional": StepNode(
                id="optional",
                tool="optional-check@1",
                in_={},
                out={"x": "state.x"},
                criticality="TRIVIAL",
                skip_permission="workflows.optional.skip",
                next="done",
            ),
        },
        endings={"done": Ending(outcome="SUCCESS", says="Done.")},
    )
    tool = Tool(
        header=_header("optional-check", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:optional"),
        effect="QUERY",
        permission="workflows.optional.dispatch",
    )
    code_tool = StubCodeToolAdapter(responses={"mod:optional": {"x": "ran"}})
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=code_tool,
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-skip-6", "root", ctx, inputs={}, host_inputs={}))
    assert answer.ending == "done"
    assert (
        code_tool.observed_calls
    )  # the Tool WAS dispatched — ADVISORY alone doesn't skip anything


# --------------------------------------------------------------- calling a process (§9) --


def test_process_call_ref_translates_outputs_and_endings():
    """§9.1's worked example, `ref` form: a `PROCESS`-mechanism STEP
    recursively drives a wholly separate, independently governed Process
    and maps its ending's final state back into this STEP's own output."""
    from sulis_workflows.definition.model import CallResult, StateChannel

    child_work_tool = Tool(
        header=_header("child-work", "TOOL"),
        output={"y": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:child_work"),
        effect="QUERY",
        inputs={"x": InputSpec(type="string")},
        permission="workflows.child-work.dispatch",
    )
    child_process = Process(
        header=_header("child-proc", "PROCESS"),
        start="do-work",
        permission="workflows.child-proc.start",
        state={"y": StateChannel(type="string", reducer="REPLACE")},
        nodes={
            "do-work": StepNode(
                id="do-work",
                tool="child-work@1",
                in_={"x": "inputs.x"},
                out={"y": "state.y"},
                end="CHILD_DONE",
            ),
        },
        endings={"CHILD_DONE": Ending(outcome="SUCCESS", says="Child done.")},
    )
    call_child_tool = Tool(
        header=_header("call-child", "TOOL"),
        output={"note": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(
            kind="PROCESS",
            ref="child-proc@1",
            inputs={"x": "inputs.seed"},
            result=CallResult(
                outputs={"note": "state.y"}, endings={"CHILD_DONE": "DONE"}
            ),
        ),
        effect="QUERY",
        permission="workflows.call-child.dispatch",
    )
    parent = Process(
        header=_header("parent-proc", "PROCESS"),
        start="call-child",
        permission="workflows.parent-proc.start",
        state={"summary": StateChannel(type="string", reducer="REPLACE")},
        nodes={
            "call-child": StepNode(
                id="call-child",
                tool="call-child@1",
                in_={},
                out={"note": "state.summary"},
                end="DONE",
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Parent done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(responses={"mod:child_work": {"y": "hello"}}),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([child_work_tool, child_process, call_child_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(
        next_(parent, "run-call-1", "root", ctx, inputs={"seed": "hi"}, host_inputs={})
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "DONE"


def test_process_call_inline_hands_off_and_resumes_via_report():
    """§9.1, anonymous form (D18): a nested hand-off (a `SKILL` Tool
    inside the inline child) bubbles up carrying the CHILD's own nested
    `scope` (§9.3), and `report()` against that scope resumes the child
    and then continues the parent — no separate "cascade up" call."""
    from sulis_workflows.definition.model import CallResult, InlineProcess, StateChannel

    skill_tool = Tool(
        header=_header("draft-note", "TOOL"),
        output={"note": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="SKILL", ref="skills/draft-note"),
        effect="QUERY",
        permission="workflows.draft-note.dispatch",
    )
    call_tool = Tool(
        header=_header("call-inline", "TOOL"),
        output={"note": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(
            kind="PROCESS",
            process=InlineProcess(
                start="draft",
                nodes={
                    "draft": StepNode(
                        id="draft",
                        tool="draft-note@1",
                        in_={},
                        out={"note": "state.note"},
                        end="INLINE_DONE",
                    ),
                },
                state={"note": StateChannel(type="string", reducer="REPLACE")},
                endings={"INLINE_DONE": Ending(outcome="SUCCESS", says="Inline done.")},
            ),
            result=CallResult(
                outputs={"note": "state.note"}, endings={"INLINE_DONE": "DONE"}
            ),
        ),
        effect="QUERY",
        permission="workflows.call-inline.dispatch",
    )
    parent = Process(
        header=_header("parent-inline", "PROCESS"),
        start="call-inline",
        permission="workflows.parent-inline.start",
        state={"summary": StateChannel(type="string", reducer="REPLACE")},
        nodes={
            "call-inline": StepNode(
                id="call-inline",
                tool="call-inline@1",
                in_={},
                out={"note": "state.summary"},
                end="DONE",
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Parent done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([skill_tool, call_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(parent, "run-inline-1", "root", ctx, inputs={}, host_inputs={}))
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "draft"
    assert answer.scope == "root/call-inline"  # §9.3 — names its OWN nested scope

    answer2 = _run(
        report(
            parent,
            "run-inline-1",
            answer.scope,
            answer.node_id,
            ctx,
            inputs={},
            host_inputs={},
            output={"note": "a draft note"},
        )
    )
    assert answer2.kind is AnswerKind.ENDED
    assert answer2.ending == "DONE"


def test_process_call_depth_exhausted_routes_to_on_depth_exhausted():
    """§9.2: a call chain deeper than the process's own `max_depth`
    (here forced to 0) never delegates at all — it routes via
    `on_depth_exhausted` instead, the same as any other STEP failure."""
    from sulis_workflows.definition.model import (
        CallResult,
        ProcessDefaults,
    )

    child_work_tool = Tool(
        header=_header("child-work", "TOOL"),
        output={"y": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:child_work"),
        effect="QUERY",
        permission="workflows.child-work.dispatch",
    )
    child_process = Process(
        header=_header("child-proc", "PROCESS"),
        start="do-work",
        permission="workflows.child-proc.start",
        nodes={
            "do-work": StepNode(
                id="do-work", tool="child-work@1", in_={}, out={}, end="CHILD_DONE"
            ),
        },
        endings={"CHILD_DONE": Ending(outcome="SUCCESS", says="Child done.")},
    )
    call_child_tool = Tool(
        header=_header("call-child", "TOOL"),
        output={"note": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(
            kind="PROCESS",
            ref="child-proc@1",
            result=CallResult(endings={"CHILD_DONE": "DONE"}),
        ),
        effect="QUERY",
        permission="workflows.call-child.dispatch",
    )
    parent = Process(
        header=_header("parent-proc", "PROCESS"),
        start="call-child",
        permission="workflows.parent-proc.start",
        defaults=ProcessDefaults(max_depth=0),
        nodes={
            "call-child": StepNode(
                id="call-child",
                tool="call-child@1",
                in_={},
                out={},
                end="DONE",
                on_depth_exhausted=RouteTarget(end="TOO_DEEP"),
            ),
        },
        endings={
            "DONE": Ending(outcome="SUCCESS", says="Parent done."),
            "TOO_DEEP": Ending(outcome="FAILURE", says="Nested too deep."),
        },
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(responses={"mod:child_work": {}}),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([child_work_tool, child_process, call_child_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(parent, "run-depth-1", "root", ctx, inputs={}, host_inputs={}))
    assert answer.ending == "TOO_DEEP"


def test_process_call_ref_child_with_no_permission_is_forbidden():
    """D14, applied to a called process the same as the run itself: a
    `ref`'d child with no `permission` is refused before it is ever
    entered, never silently run unchecked."""
    from sulis_workflows.definition.model import CallResult

    child_process = Process(
        header=_header("child-proc", "PROCESS"),
        start="do-work",
        permission=None,
        nodes={
            "do-work": StepNode(
                id="do-work", tool="child-work@1", in_={}, out={}, end="CHILD_DONE"
            ),
        },
        endings={"CHILD_DONE": Ending(outcome="SUCCESS", says="Child done.")},
    )
    child_work_tool = Tool(
        header=_header("child-work", "TOOL"),
        output={"y": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:child_work"),
        effect="QUERY",
        permission="workflows.child-work.dispatch",
    )
    call_child_tool = Tool(
        header=_header("call-child", "TOOL"),
        output={"note": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(
            kind="PROCESS",
            ref="child-proc@1",
            result=CallResult(endings={"CHILD_DONE": "DONE"}),
        ),
        effect="QUERY",
        permission="workflows.call-child.dispatch",
    )
    parent = Process(
        header=_header("parent-proc", "PROCESS"),
        start="call-child",
        permission="workflows.parent-proc.start",
        nodes={
            "call-child": StepNode(
                id="call-child",
                tool="call-child@1",
                in_={},
                out={},
                end="DONE",
                on_forbidden=RouteTarget(end="BLOCKED"),
            ),
        },
        endings={
            "DONE": Ending(outcome="SUCCESS", says="Parent done."),
            "BLOCKED": Ending(outcome="STOPPED", says="Blocked."),
        },
    )
    call_count = {"n": 0}

    class CountingAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            call_count["n"] += 1
            return {"y": "should not run"}

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=CountingAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([child_work_tool, child_process, call_child_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(parent, "run-noperm-1", "root", ctx, inputs={}, host_inputs={}))
    assert answer.ending == "BLOCKED"
    assert call_count["n"] == 0  # the child was never entered


def test_process_call_control_failure_on_translated_output_routes_via_then():
    """A control declared on the CALLING Tool checks the translated
    output the same way it would check any other Tool's output — a
    process call is not a special case for §10.2."""
    from sulis_workflows.definition.model import (
        CallResult,
        ControlFail,
        ControlRef,
        Profile,
    )

    child_work_tool = Tool(
        header=_header("child-work", "TOOL"),
        output={"y": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:child_work"),
        effect="QUERY",
        permission="workflows.child-work.dispatch",
    )
    child_process = Process(
        header=_header("child-proc", "PROCESS"),
        start="do-work",
        permission="workflows.child-proc.start",
        nodes={
            "do-work": StepNode(
                id="do-work", tool="child-work@1", in_={}, out={}, end="CHILD_DONE"
            ),
        },
        endings={"CHILD_DONE": Ending(outcome="SUCCESS", says="Child done.")},
    )
    call_child_tool = Tool(
        header=_header("call-child", "TOOL"),
        output={"note": OutputSpec(type="profile:note-shape@1")},
        controls=(ControlRef(kind="profile", ref="note-shape@1"),),
        mechanism=Mechanism(
            kind="PROCESS",
            ref="child-proc@1",
            result=CallResult(endings={"CHILD_DONE": "DONE"}),
        ),
        effect="QUERY",
        permission="workflows.call-child.dispatch",
    )
    profile = Profile(
        header=_header("note-shape", "PROFILE"),
        schema={
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string"}},
        },
    )
    parent = Process(
        header=_header("parent-proc", "PROCESS"),
        start="call-child",
        permission="workflows.parent-proc.start",
        nodes={
            "call-child": StepNode(
                id="call-child",
                tool="call-child@1",
                in_={},
                out={},
                end="DONE",
                on_control_fail=ControlFail(repair=0, then=RouteTarget(end="GAVE_UP")),
            ),
        },
        endings={
            "DONE": Ending(outcome="SUCCESS", says="Parent done."),
            "GAVE_UP": Ending(outcome="FAILURE", says="Could not fix it."),
        },
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(responses={"mod:child_work": {}}),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([child_work_tool, child_process, call_child_tool, profile]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    # `note` has no `result.outputs` mapping at all -> _evaluate never runs for
    # it, so the profile check sees `None`, which is not the required object
    # shape — control fails, and with repair=0 goes straight to `then`.
    answer = _run(
        next_(parent, "run-ctrlfail-1", "root", ctx, inputs={}, host_inputs={})
    )
    assert answer.ending == "GAVE_UP"


# ---------------------------------------------------------- state reducers (§2.3, D19) --


def test_step_writing_a_mismatched_value_to_an_append_channel_ends_cleanly() -> None:
    """D19: a write that does not fit its channel's reducer shape is refused
    and recorded as a failed attempt, not a crash out of next()/report() —
    the exact bug pressure-testing the real grounded-inquiry process found
    (a STEP writing to an APPEND channel with nothing implementing APPEND)."""
    from sulis_workflows.definition.model import StateChannel

    tool = Tool(
        header=_header("gather", "TOOL"),
        output={"findings": OutputSpec(type="list<any>")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:gather"),
        effect="QUERY",
        permission="workflows.gather.dispatch",
    )
    process = Process(
        header=_header("append-process", "PROCESS"),
        start="gather",
        permission="workflows.append-process.start",
        state={"findings": StateChannel(type="list<any>", reducer="APPEND")},
        nodes={
            "gather": StepNode(
                id="gather",
                tool="gather@1",
                in_={},
                out={"findings": "state.findings"},
                end="DONE",
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done.")},
    )
    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        # The Tool's own output field is a list, but this dispatch hands back
        # a bare string instead — the bad-but-conformant write D19 defends
        # against, not a hypothetical.
        code_tool=StubCodeToolAdapter(
            responses={"mod:gather": {"findings": "not a list"}}
        ),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-state-1", "root", ctx, inputs={}, host_inputs={}))
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "FAILED"
    assert answer.outcome == "FAILURE"


def test_step_appending_a_real_list_to_an_append_channel_accumulates() -> None:
    """The positive case for the same shape: two STEPs writing to the same
    APPEND channel accumulate rather than each replacing the other's write —
    exactly what grounded-inquiry's own gather->interrogate loop depends on.
    A third step reads `state.findings` back as its own input, so the
    assertion is on what the engine actually accumulated, not just that the
    run reached an ending without crashing."""
    from sulis_workflows.definition.model import InputSpec, StateChannel

    gather_tool = Tool(
        header=_header("gather", "TOOL"),
        output={"findings": OutputSpec(type="list<any>")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:gather"),
        effect="QUERY",
        permission="workflows.gather.dispatch",
    )
    gather_again_tool = Tool(
        header=_header("gather-again", "TOOL"),
        output={"findings": OutputSpec(type="list<any>")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:gather-again"),
        effect="QUERY",
        permission="workflows.gather.dispatch",
    )
    snapshot_tool = Tool(
        header=_header("snapshot", "TOOL"),
        output={"snapshot": OutputSpec(type="any")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:snapshot"),
        effect="QUERY",
        inputs={"findings": InputSpec(type="any")},
        permission="workflows.snapshot.dispatch",
    )
    process = Process(
        header=_header("append-process", "PROCESS"),
        start="gather",
        permission="workflows.append-process.start",
        state={
            "findings": StateChannel(type="list<any>", reducer="APPEND"),
            "snapshot": StateChannel(type="any", reducer="REPLACE"),
        },
        nodes={
            "gather": StepNode(
                id="gather",
                tool="gather@1",
                in_={},
                out={"findings": "state.findings"},
                next="gather-again",
            ),
            "gather-again": StepNode(
                id="gather-again",
                tool="gather-again@1",
                in_={},
                out={"findings": "state.findings"},
                next="snapshot",
            ),
            "snapshot": StepNode(
                id="snapshot",
                tool="snapshot@1",
                in_={"findings": "state.findings"},
                out={"snapshot": "state.snapshot"},
                end="DONE",
            ),
        },
        endings={"DONE": Ending(outcome="SUCCESS", says="Done.")},
    )

    captured: dict[str, object] = {}

    class CapturingAdapter:
        def __init__(self):
            self.identity = StubCodeToolAdapter().identity

        async def call(self, ref, inputs, *, platform_id, run_id):
            if ref == "mod:gather":
                return {"findings": ["f1"]}
            if ref == "mod:gather-again":
                return {"findings": ["f2", "f3"]}
            if ref == "mod:snapshot":
                captured["findings"] = inputs["findings"]
                return {"snapshot": inputs["findings"]}
            raise AssertionError(f"unexpected ref: {ref}")

    ctx = EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=CapturingAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=Registry([gather_tool, gather_again_tool, snapshot_tool]),
        identity="user:iain",
        platform_id="tenant-1",
    )
    answer = _run(next_(process, "run-state-2", "root", ctx, inputs={}, host_inputs={}))
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "DONE"
    assert captured["findings"] == ["f1", "f2", "f3"]
