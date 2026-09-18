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
  repaired dispatch DOES receive "the failures as input" (§10.2 step 5's
  own wording): before each repair (or retry) dispatch, the last
  attempt's controls are written to `steps.<own-id>.controls` in run
  state (§2.2's own reserved shape, `.controls.<control>.passed`,
  extended here with `.findings` — a grounded but non-literal reading,
  since §2.2 names no `.findings` sub-path itself), so the Step's own
  `in:` mapping can read what failed last time.
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
    check_agent_decision,
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
from sulis_workflows.engine.steps import StepAttemptResult, StepOutcome, attempt_step

__all__ = [
    "AnswerKind",
    "EngineContext",
    "NextAnswer",
    "decide",
    "next_",
    "report",
    "skip",
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
    instructions_ref: str | None = None
    controls: tuple[Mapping[str, str], ...] | None = None
    ending: str | None = None
    outcome: str | None = None
    skippable: bool = False


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
    `AGENTIC` Tool), OR a GATE's `agent` decider `DECISION_STEP` hand-off
    (gates.py's own docstring: an agent decider "need[s] a round trip
    through next()/report()/decide()", the same as a STEP's Tool). Records
    the attempt, checks controls (STEP) or the decision's evidence and
    separation-of-duty (GATE), then continues driving forward exactly as
    `next()` would.
    """
    node = process.nodes[node_id]
    if isinstance(node, GateNode):
        return await _report_gate_decision(
            process,
            run_id,
            scope,
            node_id,
            ctx,
            inputs=inputs,
            host_inputs=host_inputs,
            output=output,
            error_code=error_code,
        )
    if not isinstance(node, StepNode):
        raise EngineRefusal(
            f"report() called for {node_id!r}, which is not a STEP or GATE node"
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
            performed_by=f"AGENT:{tool.mechanism.ref}::{ctx.identity}",
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )
    else:
        from sulis_workflows.engine.controls import check_controls

        controls_result = await check_controls(
            tool,
            output or {},
            registry=ctx.registry,
            code_tool=ctx.code_tool,
            platform_id=ctx.platform_id,
            run_id=run_id,
        )
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
                {
                    "control": o.control.ref,
                    "passed": o.passed,
                    "findings": list(o.findings),
                }
                for o in controls_result.outcomes
            ],
            verdict=outcome.value,
            performed_by=f"AGENT:{tool.mechanism.ref}::{ctx.identity}",
            started_at=_now(),
            ended_at=_now(),
        )
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )

    return await _drive(process, run_id, scope, ctx, inputs, host_inputs)


async def _report_gate_decision(
    process: Process,
    run_id: str,
    scope: str,
    node_id: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    output: Mapping[str, Any] | None,
    error_code: str | None,
) -> NextAnswer:
    """Completes a GATE's `agent` decider `DECISION_STEP` hand-off.

    Unlike a STEP's `report()`, the actual validation (permission check,
    §7.6's evidence-path-resolves-to-a-value and no-deciding-on-your-own-
    work checks) cannot happen here directly — it needs the run's current
    state and `produced_by` history, which only `_drive`'s own replay
    holds (§12.1: nothing kept between calls). So this hands the raw
    decision to `_drive` as `pending_decision`; `_advance_gate` applies it
    at exactly the point it is reached, with the same state it would use
    to check whether the gate is even still awaiting this decider.

    If this call turns out not to actually correspond to what the gate is
    currently awaiting (a stale hand-off, a second `report()` for the same
    decider, wrong node), `_advance_gate` simply never consumes the
    decision and `_drive` returns the gate's actual current answer instead
    — no state is corrupted, but the decision is silently dropped rather
    than raising, a known rough edge (see the run record for this fix).
    """
    if error_code is not None:
        raise EngineRefusal(
            f"report() with an error_code for gate {node_id!r} is not "
            "supported — spec §7.6 does not describe an agent decider's "
            "own dispatch failing, as distinct from it returning "
            "INDETERMINATE, so nothing is invented here for that case."
        )
    if output is None:
        raise EngineRefusal(
            f"report() called for gate {node_id!r} with no decision output"
        )
    return await _drive(
        process,
        run_id,
        scope,
        ctx,
        inputs,
        host_inputs,
        pending_decision=(node_id, output),
    )


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

    §10.1: "...or accepts any decision, it asks the host's `PolicyPort`" —
    checked here before recording, the same as `_advance_step`'s STEP
    dispatch and `_advance_gate`'s agent-decider vote. Which permission:
    if `decide()` is satisfying a declared `person`-kind decider at its
    rightful sequence position, that decider's own `permission` (§7.6:
    `person: { permission: <host permission> }`); otherwise (no deciders
    declared, or every declared decider already answered INDETERMINATE)
    the gate's own `permission` (D13's fallback, §7.6: "the gate stays
    open for a person with the gate's permission"). A `person` decider
    declared with `role` instead of `permission` is refused outright —
    `PolicyPort.authorize()` has no way to check a role, only an opaque
    permission string, and nothing here invents one.
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

    permission: str | None
    if (
        decider_index < len(node.deciders)
        and node.deciders[decider_index].kind == "person"
    ):
        decider = node.deciders[decider_index]
        if decider.permission is None and decider.role is not None:
            return _forbidden(
                process,
                f"gate {gate_id!r}: person decider declares `role`, which "
                "this engine's PolicyPort cannot check (permission strings "
                "only) — refusing rather than accepting an unchecked decision.",
            )
        permission = decider.permission
    else:
        # D13: no declared decider at this slot — either none were
        # declared at all, or every declared decider has already answered
        # (the pause state) — the gate's own permission is who may decide.
        permission = node.permission

    if permission is None:
        return _forbidden(
            process,
            f"gate {gate_id!r} declares no permission for a person to "
            "decide it here — refusing rather than accepting it unchecked.",
        )
    decision = await ctx.policy.authorize(
        permission, identity=ctx.identity, platform_id=ctx.platform_id, run_id=run_id
    )
    if decision.verdict is not Verdict.PERMIT:
        return _forbidden(process, decision.rationale or "decision permission refused")

    key = AttemptKey(run=run_id, scope=scope, node=gate_id, attempt=decider_index + 1)
    record = AttemptRecord(
        key=key,
        inputs={},
        output={"note": note} if note else None,
        control_results=[],
        verdict=verdict.value,
        performed_by=f"PERSON:{subject}",
        started_at=_now(),
        ended_at=_now(),
    )
    await ctx.records.record_attempt(record, platform_id=ctx.platform_id, run_id=run_id)
    return await _drive(process, run_id, scope, ctx, inputs, host_inputs)


async def skip(
    process: Process,
    run_id: str,
    scope: str,
    node_id: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    reason: str,
    subject: str,
) -> NextAnswer:
    """§6: `ADVISORY` skip policy — "a person with permission MAY skip a
    step whose `criticality` is `TRIVIAL`, recording a reason." Not part
    of §12.1's own three named calls (the spec's engine-semantics section
    predates this being wired up); shaped the same way as `decide()` since
    it is the same kind of act — a person's recorded decision, checked
    against a permission, that changes what the run does next.

    Note the terminology: `skip_policy` (`STRICT`/`ADVISORY`) is a
    narrower thing than "guided" in the sense the format's own callers
    use it (an agent driving the run step by step via `next()`/`report()`,
    as opposed to the deprecated `compiler/` path executing a whole run
    internally) — that property holds for every run regardless of
    `skip_policy`. D16 renamed `execution_policy` to `skip_policy` and
    `GUIDED` to `ADVISORY` for exactly this reason: freeing "guided" to
    keep its one meaning instead of naming two different things.

    Fails closed on every one of D2/D15's conditions, not just the
    permission check: refuses a step that is not a `STEP` node, a process
    whose `skip_policy` is not `ADVISORY`, a step whose `criticality` is
    not `TRIVIAL` (`STANDARD`/`CRITICAL` are never skippable, §6), a step
    with no `skip_permission` declared (D15), and a call with no `reason`.

    Callable at any point before this step's own first attempt (i.e.
    before anything has called `next()`/`report()` far enough to dispatch
    it) — this engine does not itself pause and offer the choice before
    every `TRIVIAL` step; a caller wanting to prompt a person must check
    eligibility (or just read the Process definition) and call `skip()`
    itself before calling `next()`, or let `next()` proceed normally.
    """
    node = process.nodes[node_id]
    if not isinstance(node, StepNode):
        raise EngineRefusal(f"skip() called for {node_id!r}, which is not a STEP node")
    if process.skip_policy != "ADVISORY":
        raise EngineRefusal(
            f"process {process.header.id!r} has skip_policy "
            f"{process.skip_policy!r} — steps cannot be skipped (§6)"
        )
    criticality = node.criticality or fmt_defaults.STEP_CRITICALITY
    if criticality != "TRIVIAL":
        raise EngineRefusal(
            f"step {node_id!r} has criticality {criticality!r} — only TRIVIAL "
            "steps may be skipped (§6, D2)"
        )
    if node.skip_permission is None:
        raise EngineRefusal(
            f"step {node_id!r} declares no `skip_permission` — refusing to skip (D15)"
        )
    if not reason:
        raise EngineRefusal("skip() requires a non-empty `reason` (§6)")

    decision = await ctx.policy.authorize(
        node.skip_permission,
        identity=ctx.identity,
        platform_id=ctx.platform_id,
        run_id=run_id,
    )
    if decision.verdict is not Verdict.PERMIT:
        return _forbidden(process, decision.rationale or "skip permission refused")

    attempts = await ctx.records.get_attempts(
        run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
    )
    key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=len(attempts) + 1)
    record = AttemptRecord(
        key=key,
        inputs={},
        output={"reason": reason},
        control_results=[],
        verdict="SKIPPED",
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
    *,
    pending_decision: tuple[str, Mapping[str, Any]] | None = None,
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

    # §7.6's "no deciding on your own work" needs to know which identity
    # produced each reviewed state path — built up as this replay passes
    # each STEP that wrote state, from that attempt's own durable
    # `performed_by` (so it is correct on a pure replay too, not only on
    # the call where the step first ran).
    produced_by: dict[str, str] = {}

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
                    pending_decision=(
                        pending_decision[1]
                        if pending_decision is not None
                        and pending_decision[0] == node_id
                        else None
                    ),
                    produced_by=produced_by,
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
            if advance.state is not None and isinstance(node, StepNode):
                identity = _producer_identity(advance.performed_by)
                if identity is not None:
                    for path in node.out.values():
                        produced_by[path] = identity
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
    performed_by: str | None = None
    """Who/what wrote `state` on a successful STEP — `_drive` uses this to
    build `produced_by` (§7.6's "no deciding on your own work" needs to
    know which identity produced each reviewed state path, not just which
    Tool ran)."""


def _resolve_tool(ref: str, registry: Registry) -> Tool:
    tool = registry.resolve("TOOL", ref)
    assert isinstance(tool, Tool)  # V2 already guarantees this resolves
    return tool


def _producer_identity(performed_by: str | None) -> str | None:
    """Extracts the identity suffix from an `AGENT:<ref>::<identity>`
    `performed_by` string (§7.6's `produced_by`), or `None` for anything
    else (a CODE-performed step, a bare `AGENT:<ref>` with no identity
    suffix, or no `performed_by` at all).

    `::` (not a single `:`) is the separator deliberately: this
    codebase's own identity strings already contain single colons
    (`"user:iain"`, `"PERSON:<subject>"`), and a Tool's own `ref` can too
    (a CODE mechanism's `module:function`) — splitting on one `:` would
    misparse either. `::` is not used elsewhere in either half.
    """
    if performed_by is None or not performed_by.startswith("AGENT:"):
        return None
    if "::" not in performed_by:
        return None
    return performed_by.rsplit("::", 1)[-1]


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
        if last.verdict == "SKIPPED":
            # §6: an ADVISORY skip() call already recorded this — proceed as
            # the step's own declared route says, without ever dispatching
            # the Tool or writing anything into state (there is no output).
            return _Advance(next_node_id=_success_target(node))
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
                performed_by=last.performed_by,
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

        # §10.2 step 5: a repair (or retry) dispatch gets "the failures as
        # input" — §2.2's own run-state shape already reserves
        # `steps.<node>.controls.<control>.passed` for exactly this; `in:`
        # can reference it (and `.findings`, this engine's extension of
        # that shape to carry *why* a control failed, not just that it
        # did — §2.2 names no `.findings` sub-path itself, so this is a
        # grounded but non-literal reading, not a spec quotation).
        run_state["steps"][node_id] = _step_record_from(last)

    if tool.mechanism.kind != "CODE":
        # §10.1/D12: permission is checked before ANY dispatch, hand-off
        # included — a `TOOL_STEP` hand-off IS the dispatch for a `SKILL`/
        # `AGENTIC` Tool (the caller's agent session performs it next), so
        # refusing this check here rather than only inside `attempt_step`
        # (CODE-only) closes a gap where a permission-less or refused
        # non-CODE Tool was previously handed off uncontrolled.
        precheck: StepAttemptResult | None
        if tool.permission is None:
            precheck = StepAttemptResult(
                outcome=StepOutcome.FORBIDDEN,
                rationale=(
                    f"Tool {tool.header.id!r} declares no `permission` — refusing "
                    "to dispatch rather than skip the check (spec §10.1, D12)."
                ),
            )
        else:
            decision = await ctx.policy.authorize(
                tool.permission,
                identity=ctx.identity,
                platform_id=ctx.platform_id,
                run_id=run_id,
            )
            precheck = (
                None
                if decision.verdict is Verdict.PERMIT
                else StepAttemptResult(
                    outcome=StepOutcome.FORBIDDEN, rationale=decision.rationale
                )
            )
        if precheck is not None:
            return await _record_step_result(
                process,
                node,
                node_id,
                tool,
                precheck,
                attempts,
                baseline,
                run_state,
                run_id,
                scope,
                ctx,
                performed_by=f"AGENT:{tool.mechanism.ref}::{ctx.identity}",
            )

        resolved_inputs, _missing = _resolve_inputs_preview(node, tool, run_state)
        return _Advance(
            answer=NextAnswer(
                kind=AnswerKind.TOOL_STEP,
                says=f"Waiting on {node.tool} to run.",
                node_id=node_id,
                resolved_inputs=resolved_inputs,
                # §12.1: "TOOL_STEP ... resolved inputs, instructions ref,
                # controls" — `instructions_ref` is the mechanism's own
                # `ref` (§4.3: "a skill document" for SKILL, "a skill or
                # agent definition" for AGENTIC), previously only
                # reachable by the caller looking the Tool up itself via
                # `node.tool` and the registry, not carried on the answer.
                instructions_ref=tool.mechanism.ref,
                controls=tuple({"kind": c.kind, "ref": c.ref} for c in tool.controls),
                skippable=_is_skippable(process, node),
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
    return await _record_step_result(
        process,
        node,
        node_id,
        tool,
        result,
        attempts,
        baseline,
        run_state,
        run_id,
        scope,
        ctx,
        performed_by=f"CODE:{tool.mechanism.ref}",
    )


async def _record_step_result(
    process: Process,
    node: StepNode,
    node_id: str,
    tool: Tool,
    result: StepAttemptResult,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    *,
    performed_by: str,
) -> _Advance:
    """Turns one `StepAttemptResult` — whether from `attempt_step` (a real
    CODE dispatch) or a permission pre-check for a non-CODE hand-off — into
    a durable `AttemptRecord` and the resulting `_Advance`: success,
    TRANSIENT retry, CONTROL_FAILED repair, or routed failure. Shared so
    both dispatch paths get identical recording/retry/repair/routing
    semantics rather than two copies that could drift apart.
    """
    key = AttemptKey(
        run=run_id, scope=scope, node=node_id, attempt=baseline + len(attempts) + 1
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
                {
                    "control": o.control.ref,
                    "passed": o.passed,
                    "findings": list(o.findings),
                }
                for o in result.controls.outcomes
            ]
            if result.controls
            else []
        ),
        verdict=result.outcome.value,
        performed_by=performed_by,
        started_at=_now(),
        ended_at=_now(),
    )
    await ctx.records.record_attempt(record, platform_id=ctx.platform_id, run_id=run_id)

    if result.outcome is StepOutcome.SUCCESS:
        new_state = apply_output(
            process.state, run_state["state"], node.out, result.output or {}
        )
        return _Advance(
            next_node_id=_success_target(node),
            state=new_state,
            performed_by=performed_by,
        )
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


def _step_record_from(record: AttemptRecord) -> dict[str, Any]:
    """§2.2's `steps.<node>` shape: `.output.<name>`, `.verdict`,
    `.controls.<control>.passed`, `.attempt` — populated from the last
    attempt so a repair (or retry) dispatch's own `in:` mapping can read
    "the failures as input" (§10.2 step 5) via `steps.<own-id>.controls`.

    `<control>` is keyed by the control's bare id (`insight`), not its
    full `id@version` ref (`insight@1`) — the expression grammar's path
    syntax (§8, `path := ident ("." ident | "[" integer "]")*`) has no
    room for `@` in an ident, so the versioned ref itself is not a
    reachable path segment; a run only ever has one resolved version of
    a control in play, so the bare id is unambiguous within it.
    """
    return {
        "output": record.output
        if record.verdict == StepOutcome.SUCCESS.value
        else None,
        "verdict": record.verdict,
        "controls": {
            cr["control"].split("@")[0]: {
                "passed": cr["passed"],
                "findings": cr.get("findings", []),
            }
            for cr in (record.control_results or [])
        },
        "attempt": record.key.attempt,
    }


def _success_target(node: StepNode) -> str:
    if node.next is not None:
        return node.next
    if node.end is not None:
        return node.end
    raise EngineRefusal(
        f"step {node.id!r} succeeded with no `next` or `end` declared (V7 gap)"
    )


def _is_skippable(process: Process, node: StepNode) -> bool:
    """§6: structurally eligible for `skip()` — `ADVISORY` skip policy,
    TRIVIAL criticality. Does not check `skip_permission`/authorization;
    `skip()` itself enforces that at the point of the actual call, the
    same way a GATE's `on` routes are shown regardless of whether this
    particular caller holds the gate's permission."""
    criticality = node.criticality or fmt_defaults.STEP_CRITICALITY
    return process.skip_policy == "ADVISORY" and criticality == "TRIVIAL"


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
    *,
    pending_decision: Mapping[str, Any] | None,
    produced_by: Mapping[str, str],
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
            pending_decision=pending_decision,
            produced_by=produced_by,
        )

    if gate_decision.resolution is GateResolution.NEEDS_AGENT:
        assert gate_decision.next_decider_index is not None
        decider_index = gate_decision.next_decider_index
        decider = node.deciders[decider_index]

        if pending_decision is not None:
            # §10.1/D12, mirroring the STEP-side fix: the reviewing agent's
            # own permission is checked before its vote counts, the same as
            # any other Tool dispatch. An unauthorized/undeclared-permission
            # decider does not end the whole run (unlike a STEP's own
            # dispatch) — a GATE already has other deciders to fall back to
            # by design (policy, then agent, then person), so this decider
            # simply cannot contribute a vote: INDETERMINATE, which
            # `resolve_gate` already treats as "ask the next decider".
            assert decider.ref is not None  # V9 requires `agent: <ref>` to declare one
            tool = _resolve_tool(decider.ref, ctx.registry)
            permission_rationale: str | None = None
            if tool.permission is None:
                permission_rationale = (
                    f"Tool {tool.header.id!r} declares no `permission` — "
                    "refusing to count this decider's vote (spec §10.1, D12)."
                )
            else:
                perm_decision = await ctx.policy.authorize(
                    tool.permission,
                    identity=ctx.identity,
                    platform_id=ctx.platform_id,
                    run_id=run_id,
                )
                if perm_decision.verdict is not Verdict.PERMIT:
                    permission_rationale = (
                        perm_decision.rationale or "agent decider permission refused"
                    )

            if permission_rationale is not None:
                outcome = DeciderOutcome(
                    decider_index=decider_index,
                    verdict=Verdict.INDETERMINATE,
                    decided_by=f"AGENT:{decider.ref}:{ctx.identity}",
                    rationale=permission_rationale,
                )
            else:
                outcome = check_agent_decision(
                    pending_decision,
                    decider,
                    decider_index,
                    gate=node,
                    run_state=run_state,
                    agent_session_id=ctx.identity,
                    produced_by=produced_by,
                )

            key = AttemptKey(
                run=run_id,
                scope=scope,
                node=node_id,
                attempt=baseline + decider_index + 1,
            )
            record = AttemptRecord(
                key=key,
                inputs={},
                output={
                    "evidence": list(outcome.evidence),
                    "rationale": outcome.rationale,
                },
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
                pending_decision=None,
                produced_by=produced_by,
            )

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
