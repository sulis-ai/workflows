"""next() / report() / decide() — the stateless engine contract (spec §12.1, WP-02 step 5).

"Starting and resuming are the same call. Nothing is held in memory
between calls." This module honours that literally: every call
reconstructs the run's current position and state by replaying every
node's durable attempt records from `process.start` forward
(`_drive`), rather than reading any state this process instance might
still be holding from an earlier call. A second process calling `next()`
against the same `RecordsPort` backend reaches the same answer — that is
the property this module exists to prove, not merely assert.

Scope (mirrors steps 2-4's own narrowing, for the same reason — an
honest, tested slice over a guessed-at complete one):

- `STEP`: only `CODE`-mechanism Tools are dispatched inline; `SKILL`/
  `AGENTIC` Tools are handed off as `TOOL_STEP` for the caller's agent
  session to run and `report()` back.
- `ROUTE`: full support (`engine/routes.py`).
- `GATE`: the `policy` decider runs inline; `agent`/`person` deciders are
  handed off as `DECISION_STEP`/`AWAITING_DECISION` for `report()`/
  `decide()` to complete.
- State writes: `REPLACE` reducer only (`engine/state.py`).
- Loop budgets: `engine/routes.py`'s `check_loop_budget`, with the taken
  count read from how many attempts the looping node already has.
- `PARALLEL`/`JOIN`/`FOR_EACH`, calling a process, triggers and templates
  are all out of WP-02's scope (`docs/work-packages/WP-02-execution-engine.md`)
  and refuse cleanly rather than being mishandled.
- `on_control_fail`'s `repair` count IS tracked (counting consecutive
  `CONTROL_FAILED` attempts within the current visit, from the node's own
  attempt records): up to `repair` further dispatches before `then`. The
  repaired dispatch does NOT yet receive "the failures as input" (§10.2
  step 5's own wording) — it re-runs with the same inputs, not fed the
  prior control findings — a smaller, separately flagged gap.
- Loop budgets (`check_loop_budget`) are enforced for both `ROUTE`
  targets (counting how many times the route has matched) and a `GATE`'s
  own looping verdict route (counting how many times THIS gate has
  resolved to that specific looping verdict, tracked separately from how
  many deciders were asked across however many askings — `_drive`'s
  `gate_loop_taken`).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition.model import (
    Ending,
    GateNode,
    Process,
    RouteNode,
    RouteTarget,
    StepNode,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.claims import ClaimsPort, ClaimStatus
from sulis_workflows.domain.ports.code_tool import CodeToolPort
from sulis_workflows.domain.ports.policy import PolicyPort, Verdict
from sulis_workflows.domain.ports.records import AttemptKey, AttemptRecord, RecordsPort
from sulis_workflows.engine.gates import (
    DeciderOutcome,
    GateResolution,
    evaluate_policy_decider,
    resolve_gate,
)
from sulis_workflows.engine.routes import (
    LoopBudgetOutcome,
    RouteOutcome,
    check_loop_budget,
    evaluate_route,
)
from sulis_workflows.engine.state import apply_output
from sulis_workflows.engine.steps import StepOutcome, attempt_step

__all__ = [
    "AnswerKind",
    "EngineContext",
    "NextAnswer",
    "decide",
    "next_",
    "report",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class EngineContext:
    """The port bundle + tenancy every call in this module needs.

    Bundled rather than five separate parameters per call, since every
    function here needs all five. ``lease_seconds`` is a host setting
    (spec §18, D3 — "not in the format"), not a format default; 300s is
    this engine's own placeholder until a host configures its own.
    """

    policy: PolicyPort
    code_tool: CodeToolPort
    records: RecordsPort
    claims: ClaimsPort
    registry: Registry
    identity: str
    platform_id: str
    lease_seconds: float = 300.0


class AnswerKind(str, Enum):
    """§12.1's exact answer vocabulary."""

    TOOL_STEP = "TOOL_STEP"
    DECISION_STEP = "DECISION_STEP"
    AWAITING_DECISION = "AWAITING_DECISION"
    STEP_RUNNING = "STEP_RUNNING"
    ENDED = "ENDED"


@dataclass(frozen=True)
class NextAnswer:
    kind: AnswerKind
    says: str
    node_id: str | None = None
    resolved_inputs: Mapping[str, Any] | None = None
    ending: str | None = None
    outcome: str | None = None


class EngineRefusal(Exception):
    """Raised internally for a shape this engine cannot run (out of WP-02's
    scope, or a structural failure with nowhere declared to route it) —
    always caught at the top of `_drive` and turned into a `FAILED` ending,
    never left to propagate as a bare exception."""


async def next_(
    process: Process,
    run_id: str,
    scope: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
) -> NextAnswer:
    """§12.1: `next(run, scope)`. Starting and resuming are this same call."""
    return await _drive(process, run_id, scope, ctx, inputs, host_inputs)


async def report(
    process: Process,
    run_id: str,
    scope: str,
    node_id: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    output: Mapping[str, Any] | None = None,
    error_code: str | None = None,
) -> NextAnswer:
    """§12.1: `report(run, scope, node, output | error)` — completes a
    `TOOL_STEP` the caller's agent session ran externally (a `SKILL`/
    `AGENTIC` Tool). Records the attempt, checks controls, then continues
    driving forward exactly as `next()` would.
    """
    node = process.nodes[node_id]
    if not isinstance(node, StepNode):
        raise EngineRefusal(
            f"report() called for {node_id!r}, which is not a STEP node"
        )
    tool = _resolve_tool(node.tool, ctx.registry)

    attempts = await ctx.records.get_attempts(
        run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
    )
    key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=len(attempts) + 1)

    if error_code is not None:
        outcome = StepOutcome.ERROR
        error_class = _classify_error(tool, error_code)
        record = AttemptRecord(
            key=key,
            inputs={},
            output={"error_code": error_code, "error_class": error_class},
            control_results=[],
            verdict=outcome.value,
            performed_by=f"AGENT:{tool.mechanism.ref}",
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )
    else:
        from sulis_workflows.engine.controls import check_controls

        controls_result = check_controls(tool, output or {}, registry=ctx.registry)
        if not controls_result.checkable:
            outcome = StepOutcome.CONTROLS_UNCHECKABLE
        elif controls_result.all_passed:
            outcome = StepOutcome.SUCCESS
        else:
            outcome = StepOutcome.CONTROL_FAILED
        record = AttemptRecord(
            key=key,
            inputs={},
            output=dict(output or {}),
            control_results=[
                {"control": o.control.ref, "passed": o.passed}
                for o in controls_result.outcomes
            ],
            verdict=outcome.value,
            performed_by=f"AGENT:{tool.mechanism.ref}",
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )

    return await _drive(process, run_id, scope, ctx, inputs, host_inputs)


async def decide(
    process: Process,
    run_id: str,
    scope: str,
    gate_id: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    verdict: Verdict,
    note: str | None,
    subject: str,
) -> NextAnswer:
    """§12.1: `decide(run, scope, gate, verdict, note)` — records a
    person's decision (identity from the caller) and continues driving
    forward.
    """
    node = process.nodes[gate_id]
    if not isinstance(node, GateNode):
        raise EngineRefusal(
            f"decide() called for {gate_id!r}, which is not a GATE node"
        )

    attempts = await ctx.records.get_attempts(
        run_id, scope, gate_id, platform_id=ctx.platform_id, run_id=run_id
    )
    decider_index = len(attempts)
    key = AttemptKey(run=run_id, scope=scope, node=gate_id, attempt=decider_index + 1)
    record = AttemptRecord(
        key=key,
        inputs={},
        output=None,
        control_results=[],
        verdict=verdict.value,
        performed_by=f"PERSON:{subject}",
        started_at=_now(),
        ended_at=_now(),
    )
    await ctx.records.record_attempt(record, platform_id=ctx.platform_id, run_id=run_id)
    return await _drive(process, run_id, scope, ctx, inputs, host_inputs)


# --------------------------------------------------------------------------- driving --


async def _drive(
    process: Process,
    run_id: str,
    scope: str,
    ctx: EngineContext,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
) -> NextAnswer:
    if process.permission is None:
        return _forbidden(
            process, "this process declares no `permission` — refusing to start (D14)."
        )
    decision = await ctx.policy.authorize(
        process.permission,
        identity=ctx.identity,
        platform_id=ctx.platform_id,
        run_id=run_id,
    )
    if decision.verdict is not Verdict.PERMIT:
        return _forbidden(process, decision.rationale or "permission refused")

    state: dict[str, Any] = {
        name: (channel.default if channel.has_default else None)
        for name, channel in process.state.items()
    }
    steps: dict[str, Any] = {}
    node_id = process.start

    # A loop can send control back to a node this same call has already
    # visited — `get_attempts` always returns every attempt this node has
    # EVER had, across every visit. `visit_baseline` remembers, per node,
    # how many of those belonged to a PRIOR visit, so each fresh visit only
    # ever sees the attempts that are actually its own (an empty slice the
    # first time this visit reaches this node, however many attempts an
    # earlier visit left behind).
    visit_baseline: dict[str, int] = {}

    # A GATE's own looping verdict (S7.6's own worked example loops on
    # DENY) needs its taken-count kept separately from `visit_baseline`,
    # which counts DECIDER attempts, not full gate resolutions — several
    # decider attempts can belong to one resolution, or one.
    gate_loop_taken: dict[str, int] = {}

    try:
        while True:
            if node_id not in process.nodes:
                return _ending_answer(process, node_id)

            node = process.nodes[node_id]
            all_attempts = await ctx.records.get_attempts(
                run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
            )
            baseline = visit_baseline.get(node_id, 0)
            visit_attempts = all_attempts[baseline:]
            run_state = {
                "inputs": inputs,
                "host": host_inputs,
                "state": state,
                "steps": steps,
            }

            if isinstance(node, StepNode):
                advance = await _advance_step(
                    process,
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                )
            elif isinstance(node, RouteNode):
                advance = await _advance_route(
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                )
            elif isinstance(node, GateNode):
                advance = await _advance_gate(
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    gate_loop_taken.get(node_id, 0),
                    run_state,
                    run_id,
                    scope,
                    ctx,
                )
                if advance.took_loop:
                    gate_loop_taken[node_id] = gate_loop_taken.get(node_id, 0) + 1
            else:
                raise EngineRefusal(
                    f"node {node_id!r} is a {type(node).__name__} node — PARALLEL/JOIN/"
                    "FOR_EACH are not supported by this engine yet (WP-03)."
                )

            if advance.answer is not None:
                return advance.answer

            state = advance.state if advance.state is not None else state
            steps[node_id] = (
                advance.step_record
                if advance.step_record is not None
                else steps.get(node_id)
            )
            # This visit is done — the next time (if ever) this same node_id
            # comes up in this call, it is a genuinely new visit.
            refreshed = await ctx.records.get_attempts(
                run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
            )
            visit_baseline[node_id] = len(refreshed)
            node_id = advance.next_node_id  # type: ignore[assignment]
    except EngineRefusal as exc:
        return NextAnswer(
            kind=AnswerKind.ENDED, says=str(exc), ending="FAILED", outcome="FAILURE"
        )


@dataclass
class _Advance:
    answer: NextAnswer | None = None
    next_node_id: str | None = None
    state: dict[str, Any] | None = None
    step_record: Mapping[str, Any] | None = None
    took_loop: bool = False


def _resolve_tool(ref: str, registry: Registry) -> Tool:
    tool = registry.resolve("TOOL", ref)
    assert isinstance(tool, Tool)  # V2 already guarantees this resolves
    return tool


def _classify_error(tool: Tool, code: str) -> str:
    for error_spec in tool.errors:
        if error_spec.code == code:
            return error_spec.error_class
    return "PERMANENT"


def _forbidden(process: Process, rationale: str) -> NextAnswer:
    return NextAnswer(
        kind=AnswerKind.ENDED,
        says=fmt_defaults.ENGINE_ENDING_SENTENCES["FORBIDDEN"],
        ending="FORBIDDEN",
        outcome="STOPPED",
    )


def _ending_answer(process: Process, ending_id: str) -> NextAnswer:
    declared = process.endings.get(ending_id)
    if isinstance(declared, Ending):
        return NextAnswer(
            kind=AnswerKind.ENDED,
            says=declared.says,
            ending=ending_id,
            outcome=declared.outcome,
        )
    sentence = fmt_defaults.ENGINE_ENDING_SENTENCES.get(ending_id)
    if sentence is not None:
        outcome = "STOPPED" if ending_id in ("FORBIDDEN", "CANCELLED") else "FAILURE"
        return NextAnswer(
            kind=AnswerKind.ENDED, says=sentence, ending=ending_id, outcome=outcome
        )
    raise EngineRefusal(
        f"{ending_id!r} is neither a node nor a declared or engine ending"
    )


def _resolve_route_target(target: RouteTarget) -> str:
    if target.next is not None:
        return target.next
    if target.end is not None:
        return target.end
    raise EngineRefusal(
        "a route target has neither `next` nor `end` — refusing (V9/V6 gap)"
    )


# ------------------------------------------------------------------------------ STEP --


async def _advance_step(
    process: Process,
    node: StepNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
) -> _Advance:
    tool = _resolve_tool(node.tool, ctx.registry)

    if attempts:
        last = attempts[-1]
        outcome = (
            _parse_step_outcome(last.verdict) if last.verdict is not None else None
        )
        if outcome is StepOutcome.ERROR:
            error_class = (last.output or {}).get("error_class", "PERMANENT")
            retry = node.retry
            max_retries = (
                retry.max if retry and retry.max is not None else fmt_defaults.RETRY_MAX
            )
            if error_class == "TRANSIENT" and len(attempts) <= max_retries:
                pass  # fall through to dispatch another attempt below
            else:
                return _Advance(next_node_id=_route_for_step_failure(node, last, tool))
        elif outcome is StepOutcome.SUCCESS:
            new_state = apply_output(
                process.state, run_state["state"], node.out, last.output or {}
            )
            return _Advance(
                next_node_id=_success_target(node),
                state=new_state,
                step_record={"output": last.output, "attempt": len(attempts)},
            )
        elif outcome is StepOutcome.CONTROL_FAILED:
            if _repair_count(attempts) <= _repair_budget(node):
                pass  # fall through to dispatch another (repair) attempt below
            else:
                return _Advance(next_node_id=_route_for_step_failure(node, last, tool))
        elif outcome in (
            StepOutcome.CONTROLS_UNCHECKABLE,
            StepOutcome.FORBIDDEN,
            StepOutcome.PRECONDITION_FALSE,
            StepOutcome.NOT_DISPATCHABLE,
            StepOutcome.INPUT_UNRESOLVED,
        ):
            return _Advance(next_node_id=_route_for_step_failure(node, last, tool))
        # outcome is None (a hand-off record already exists, e.g. from report()) —
        # treated as resolved above via the branches; fall through only for TRANSIENT retry.

    if tool.mechanism.kind != "CODE":
        resolved_inputs, _missing = _resolve_inputs_preview(node, tool, run_state)
        return _Advance(
            answer=NextAnswer(
                kind=AnswerKind.TOOL_STEP,
                says=f"Waiting on {node.tool} to run.",
                node_id=node_id,
                resolved_inputs=resolved_inputs,
            )
        )

    key = AttemptKey(
        run=run_id, scope=scope, node=node_id, attempt=baseline + len(attempts) + 1
    )
    if tool.effect in ("MUTATION", "SIDE_EFFECT"):
        claim = await ctx.claims.acquire(
            key,
            lease_seconds=ctx.lease_seconds,
            claimed_by=ctx.identity,
            platform_id=ctx.platform_id,
            run_id=run_id,
        )
        if claim.status is ClaimStatus.STEP_RUNNING:
            return _Advance(
                answer=NextAnswer(
                    kind=AnswerKind.STEP_RUNNING,
                    says="This step is already running.",
                    node_id=node_id,
                )
            )

    result = await attempt_step(
        node,
        tool,
        run_state,
        identity=ctx.identity,
        platform_id=ctx.platform_id,
        run_id=run_id,
        policy=ctx.policy,
        code_tool=ctx.code_tool,
        registry=ctx.registry,
    )
    record = AttemptRecord(
        key=key,
        inputs={},
        output=(
            dict(result.output)
            if result.outcome is StepOutcome.SUCCESS and result.output
            else (
                {"error_code": result.error_code, "error_class": result.error_class}
                if result.outcome is StepOutcome.ERROR
                else None
            )
        ),
        control_results=(
            [
                {"control": o.control.ref, "passed": o.passed}
                for o in result.controls.outcomes
            ]
            if result.controls
            else []
        ),
        verdict=result.outcome.value,
        performed_by=f"CODE:{tool.mechanism.ref}",
        started_at=_now(),
        ended_at=_now(),
    )
    await ctx.records.record_attempt(record, platform_id=ctx.platform_id, run_id=run_id)

    if result.outcome is StepOutcome.SUCCESS:
        new_state = apply_output(
            process.state, run_state["state"], node.out, result.output or {}
        )
        return _Advance(next_node_id=_success_target(node), state=new_state)
    if result.outcome is StepOutcome.ERROR and result.error_class == "TRANSIENT":
        retry = node.retry
        max_retries = (
            retry.max if retry and retry.max is not None else fmt_defaults.RETRY_MAX
        )
        if len(attempts) + 1 <= max_retries:
            return await _advance_step(
                process,
                node,
                node_id,
                attempts + [record],
                baseline,
                run_state,
                run_id,
                scope,
                ctx,
            )
    if result.outcome is StepOutcome.CONTROL_FAILED and _repair_count(
        attempts + [record]
    ) <= _repair_budget(node):
        return await _advance_step(
            process,
            node,
            node_id,
            attempts + [record],
            baseline,
            run_state,
            run_id,
            scope,
            ctx,
        )
    return _Advance(next_node_id=_route_for_step_failure(node, record, tool))


def _parse_step_outcome(value: str) -> StepOutcome | None:
    try:
        return StepOutcome(value)
    except ValueError:
        return None


def _repair_budget(node: StepNode) -> int:
    control_fail = node.on_control_fail
    if control_fail is not None and control_fail.repair is not None:
        return control_fail.repair
    return fmt_defaults.REPAIR_BUDGET


def _repair_count(attempts: list[AttemptRecord]) -> int:
    """§10.2 step 5: "up to `repair` further invocations." Counts every
    `CONTROL_FAILED` attempt already made this visit — the repair budget
    bounds how many of those are allowed before `then` is taken."""
    return sum(
        1
        for a in attempts
        if a.verdict is not None
        and _parse_step_outcome(a.verdict) is StepOutcome.CONTROL_FAILED
    )


def _success_target(node: StepNode) -> str:
    if node.next is not None:
        return node.next
    if node.end is not None:
        return node.end
    raise EngineRefusal(
        f"step {node.id!r} succeeded with no `next` or `end` declared (V7 gap)"
    )


def _resolve_inputs_preview(
    node: StepNode, tool: Tool, run_state: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    from sulis_workflows.engine.steps import _resolve_inputs

    return _resolve_inputs(node.in_, tool, run_state)


def _route_for_step_failure(node: StepNode, record: AttemptRecord, tool: Tool) -> str:
    outcome_value = record.verdict
    target: RouteTarget | None
    if outcome_value == StepOutcome.FORBIDDEN.value:
        target = node.on_forbidden or RouteTarget(end=fmt_defaults.ON_FORBIDDEN)
        return _resolve_route_target(target)
    if outcome_value == StepOutcome.PRECONDITION_FALSE.value:
        target = node.on_precondition_false or RouteTarget(
            end=fmt_defaults.ON_PRECONDITION_FALSE
        )
        return _resolve_route_target(target)
    if outcome_value in (
        StepOutcome.CONTROL_FAILED.value,
        StepOutcome.CONTROLS_UNCHECKABLE.value,
    ):
        control_fail = node.on_control_fail
        target = (
            control_fail.then
            if control_fail and control_fail.then
            else RouteTarget(end=fmt_defaults.CONTROL_FAIL_THEN)
        )
        return _resolve_route_target(target)
    if outcome_value == StepOutcome.ERROR.value:
        error_code = (record.output or {}).get("error_code")
        target = node.on_error.get(error_code) if error_code else None
        return _resolve_route_target(target or RouteTarget(end=fmt_defaults.ON_ERROR))
    raise EngineRefusal(
        f"step {node.id!r}: no route declared for outcome {outcome_value!r}"
    )


# ----------------------------------------------------------------------------- ROUTE --


async def _advance_route(
    node: RouteNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
) -> _Advance:
    target: RouteTarget | None
    if not attempts:
        decision = evaluate_route(node, run_state)
        if decision.outcome is RouteOutcome.REFUSED:
            raise EngineRefusal(decision.rationale or f"route {node_id!r} refused")
        key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=baseline + 1)
        record = AttemptRecord(
            key=key,
            inputs={},
            output={"matched_index": decision.matched_index},
            control_results=[],
            verdict=decision.outcome.value,
            performed_by="ENGINE:route",
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )
        attempts = [record]
        target = decision.target
    else:
        matched_index = (attempts[-1].output or {}).get("matched_index")
        target = (
            RouteTarget(
                next=node.when[matched_index].next,
                end=node.when[matched_index].end,
                loop=node.when[matched_index].loop,
            )
            if matched_index is not None
            else node.otherwise
        )

    assert target is not None
    if target.loop is not None:
        # Loop budgets accumulate across every PAST visit to this route, not
        # just this one — `baseline` (prior visits' own attempt, one each)
        # plus this visit's own attempts-so-far (always 1, minus the one
        # being evaluated right now) is the count taken strictly BEFORE this
        # occurrence, which is what decides whether taking it again (now) is
        # still within budget.
        prior_taken_count = baseline + len(attempts) - 1
        budget_decision = check_loop_budget(
            target.loop, taken_count=prior_taken_count, process_default_budget=None
        )
        if budget_decision.outcome is LoopBudgetOutcome.EXHAUSTED:
            return _Advance(
                next_node_id=_resolve_route_target(budget_decision.on_exhausted)
            )

    return _Advance(next_node_id=_resolve_route_target(target))


# ------------------------------------------------------------------------------ GATE --


async def _advance_gate(
    node: GateNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    prior_loop_takes: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
) -> _Advance:
    outcomes = [_outcome_from_record(index, rec) for index, rec in enumerate(attempts)]
    person_required = node.person_required_when is not None and bool(
        _evaluate(node.person_required_when, run_state)
    )
    gate_decision = resolve_gate(node, outcomes, person_required=person_required)

    if gate_decision.resolution is GateResolution.DECIDED:
        assert gate_decision.verdict is not None  # DECIDED always carries a verdict
        target = node.on.get(gate_decision.verdict.value)
        if target is None:
            raise EngineRefusal(
                f"gate {node_id!r}: no route declared for verdict "
                f"{gate_decision.verdict.value!r}"
            )
        if target.loop is not None:
            budget_decision = check_loop_budget(
                target.loop, taken_count=prior_loop_takes, process_default_budget=None
            )
            if budget_decision.outcome is LoopBudgetOutcome.EXHAUSTED:
                return _Advance(
                    next_node_id=_resolve_route_target(budget_decision.on_exhausted)
                )
            return _Advance(next_node_id=_resolve_route_target(target), took_loop=True)
        return _Advance(next_node_id=_resolve_route_target(target))

    if gate_decision.resolution is GateResolution.NEEDS_POLICY:
        assert gate_decision.next_decider_index is not None
        decider = node.deciders[gate_decision.next_decider_index]
        outcome = await evaluate_policy_decider(
            decider,
            gate_decision.next_decider_index,
            reviewing=run_state,
            identity=ctx.identity,
            platform_id=ctx.platform_id,
            run_id=run_id,
            policy=ctx.policy,
        )
        key = AttemptKey(
            run=run_id,
            scope=scope,
            node=node_id,
            attempt=baseline + gate_decision.next_decider_index + 1,
        )
        record = AttemptRecord(
            key=key,
            inputs={},
            output={"evidence": list(outcome.evidence)},
            control_results=[],
            verdict=outcome.verdict.value,
            performed_by=outcome.decided_by,
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )
        return await _advance_gate(
            node,
            node_id,
            attempts + [record],
            baseline,
            prior_loop_takes,
            run_state,
            run_id,
            scope,
            ctx,
        )

    if gate_decision.resolution is GateResolution.NEEDS_AGENT:
        assert gate_decision.next_decider_index is not None
        decider = node.deciders[gate_decision.next_decider_index]
        return _Advance(
            answer=NextAnswer(
                kind=AnswerKind.DECISION_STEP,
                says=node.asks or "A decision is needed.",
                node_id=node_id,
                resolved_inputs={
                    "agent_tool": decider.ref,
                    "criteria": node.criteria,
                    "reviewing": list(node.reviewing),
                },
            )
        )

    if gate_decision.resolution is GateResolution.NEEDS_PERSON:
        return _Advance(
            answer=NextAnswer(
                kind=AnswerKind.AWAITING_DECISION,
                says=node.asks or "A decision is needed.",
                node_id=node_id,
            )
        )

    # PAUSED — every decider asked, all INDETERMINATE (or none declared).
    return _Advance(
        answer=NextAnswer(
            kind=AnswerKind.AWAITING_DECISION,
            says=node.asks or "A decision is needed.",
            node_id=node_id,
        )
    )


def _outcome_from_record(index: int, record: AttemptRecord) -> DeciderOutcome:
    return DeciderOutcome(
        decider_index=index,
        verdict=Verdict(record.verdict),
        decided_by=record.performed_by,
        evidence=tuple((record.output or {}).get("evidence", ())),
    )


def _evaluate(expr: str, run_state: Mapping[str, Any]) -> Any:
    from sulis_workflows.definition.expressions import evaluate, parse

    return evaluate(parse(expr), run_state)
