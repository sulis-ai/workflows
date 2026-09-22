"""next() / report() / decide() — the stateless engine contract (spec §12.1, WP-02 step 5).

"Starting and resuming are the same call. Nothing is held in memory
between calls." This module honours that literally: every call
reconstructs the run's current position and state by replaying every
node's durable attempt records from `process.start` (or, for a nested
scope, the child scope's own `start`) forward (`_drive_scope`), rather
than reading any state this process instance might still be holding
from an earlier call. A second process calling `next()` against the
same `RecordsPort` backend reaches the same answer — that is the
property this module exists to prove, not merely assert.

Scope (mirrors steps 2-4's own narrowing, for the same reason — an
honest, tested slice over a guessed-at complete one):

- `STEP`: only `CODE`-mechanism Tools are dispatched inline; `SKILL`
  Tools are handed off as `TOOL_STEP` for the caller's agent session to
  run and `report()` back.
- `ROUTE`: full support (`engine/routes.py`).
- `GATE`: the `policy` decider runs inline; `agent`/`person` deciders are
  handed off as `DECISION_STEP`/`AWAITING_DECISION` for `report()`/
  `decide()` to complete.
- Calling a process (§9): both `ref`'d and inline (D18) `PROCESS`-
  mechanism STEPs are driven recursively (`_advance_process_call`,
  `_drive_scope`) — a nested scope's own hand-off bubbles up with its
  own `scope` (§9.3) for `report()`/`decide()` to target directly. §9.1's
  `path` override is not yet supported and refuses cleanly rather than
  being silently ignored.
- State writes: all four reducers spec §2.3 names — `REPLACE`, `MERGE`,
  `APPEND`, `UPSERT_BY_ID` (`engine/state.py`, D19).
- Loop budgets: `engine/routes.py`'s `check_loop_budget`, with the taken
  count read from how many attempts the looping node already has.
- `PARALLEL`/`JOIN`/`FOR_EACH`, triggers and templates are all out of
  WP-02's scope (`docs/work-packages/WP-02-execution-engine.md`) and
  refuse cleanly rather than being mishandled.
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
  many deciders were asked across however many askings — `_drive_scope`'s
  `gate_loop_taken`).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition.expressions import (
    TAny,
    TBoolean,
    TEnum,
    TInteger,
    TList,
    TMap,
    TNumber,
    TProfile,
    TString,
    Type,
    evaluate,
    parse,
    parse_type,
)
from sulis_workflows.definition.model import (
    CollectSpec,
    ComposeItem,
    Decider,
    Ending,
    ForEachNode,
    GateNode,
    JoinNode,
    Mechanism,
    Node,
    ParallelNode,
    Process,
    RouteNode,
    RouteTarget,
    StateChannel,
    StepNode,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.claims import Claim, ClaimsPort, ClaimStatus
from sulis_workflows.domain.ports.code_tool import CodeToolPort
from sulis_workflows.domain.ports.external_tool import ExternalToolPort
from sulis_workflows.domain.ports.policy import PolicyPort, Verdict
from sulis_workflows.domain.ports.records import (
    AttemptKey,
    AttemptRecord,
    DuplicateAttempt,
    RecordsPort,
)
from sulis_workflows.engine.gates import (
    AnswerOutcome,
    DeciderOutcome,
    GateResolution,
    check_agent_decision,
    evaluate_policy_decider,
    resolve_gate,
    resolve_input_gate,
)
from sulis_workflows.engine.routes import (
    LoopBudgetOutcome,
    RouteOutcome,
    check_loop_budget,
    evaluate_route,
)
from sulis_workflows.engine.state import ReducerMismatch, apply_output
from sulis_workflows.engine.steps import StepAttemptResult, StepOutcome, attempt_step

__all__ = [
    "AnswerKind",
    "EngineContext",
    "HeartbeatAnswer",
    "NextAnswer",
    "decide",
    "heartbeat",
    "next_",
    "report",
    "skip",
]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class EngineContext:
    """The port bundle + tenancy every call in this module needs.

    Bundled rather than several separate parameters per call, since every
    function here needs all of them. ``lease_seconds`` is a host setting
    (spec §18, D3 — "not in the format"), not a format default; 300s is
    this engine's own placeholder until a host configures its own.
    ``external_tool`` (WP-04 Part 1) is a distinct port from ``code_tool``
    even though both dispatch a Tool call the same way — see
    ``domain/ports/external_tool.py``'s own module docstring for why the
    two are kept separate rather than one port reused under two names.
    """

    policy: PolicyPort
    code_tool: CodeToolPort
    external_tool: ExternalToolPort
    records: RecordsPort
    claims: ClaimsPort
    registry: Registry
    identity: str
    platform_id: str
    lease_seconds: float = 300.0


async def _record_attempt(
    ctx: EngineContext, record: AttemptRecord, *, run_id: str
) -> None:
    """Write this attempt, or confirm someone else already did.

    `RecordsPort.record_attempt` raises `DuplicateAttempt` on a second
    write to the same `AttemptKey` (§12.2's write-once guard). Attempt
    numbers are derived deterministically from replay position (how many
    attempts this node's current visit has already consumed), so two
    calls racing to record the SAME key can only be resolving the SAME
    logical attempt — the same "second process calling next() against the
    same RecordsPort backend reaches the same answer" property §12.1
    already requires of the read side. Swallowing the collision here is
    that property's write-side counterpart: the durable row this call
    wanted to create already exists either way, and every caller already
    has its own local `record` to keep using — none of them read
    `record_attempt`'s return value (`None` either way)."""
    try:
        await ctx.records.record_attempt(
            record, platform_id=ctx.platform_id, run_id=run_id
        )
    except DuplicateAttempt:
        pass


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
    # §9.3: "every answer names the scope and definition it belongs to, at
    # any depth" — the scope this answer's `node_id` is relative to, so a
    # caller resuming a hand-off bubbled up from a nested PROCESS call
    # knows which scope to target `report()`/`decide()` at, rather than
    # assuming the top-level one. Unset on an `ENDED` answer (no node to
    # target).
    scope: str | None = None
    resolved_inputs: Mapping[str, Any] | None = None
    instructions_ref: str | None = None
    controls: tuple[Mapping[str, str], ...] | None = None
    ending: str | None = None
    outcome: str | None = None
    skippable: bool = False


class EngineRefusal(Exception):
    """Raised internally for a shape this engine cannot run (out of WP-02's
    scope, or a structural failure with nowhere declared to route it) —
    always caught at the top of `_drive_scope` and turned into a `FAILED`
    ending, never left to propagate as a bare exception."""


async def next_(
    process: Process,
    run_id: str,
    scope: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
) -> NextAnswer:
    """§12.1: `next(run, scope)`. Starting and resuming are this same call.

    `scope` may itself already name a nested level (§9.3) — driving
    always restarts from that scope's own top segment regardless, since
    replay naturally re-descends into whichever nested level is still
    open (see `_drive_scope`'s own docstring).
    """
    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
    )
    return result.answer


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
    `TOOL_STEP` the caller's agent session ran externally (a `SKILL`
    Tool), OR a GATE's `agent` decider `DECISION_STEP` hand-off
    (gates.py's own docstring: an agent decider "need[s] a round trip
    through next()/report()/decide()", the same as a STEP's Tool). Records
    the attempt, checks controls (STEP) or the decision's evidence and
    separation-of-duty (GATE), then continues driving forward exactly as
    `next()` would.

    WP-04 Part 2: a composed `SKILL` child's own hand-off (`_advance_compose`)
    names itself `f"{outer_node_id}.compose[{i}]"`, in the SAME scope as its
    own composite STEP (not a nested one — see `_advance_compose`'s own
    docstring for why) — checked here, before the ordinary `scope_def.nodes`
    lookup, since a synthetic compose-child id is never a real node.
    """
    compose_match = _COMPOSE_CHILD_NODE_ID_RE.match(node_id)
    if compose_match:
        return await _report_compose_child(
            process,
            run_id,
            scope,
            compose_match.group("outer"),
            int(compose_match.group("index")),
            ctx,
            inputs=inputs,
            host_inputs=host_inputs,
            output=output,
            error_code=error_code,
        )
    scope_def = _resolve_scope(process, scope, ctx.registry)
    node = scope_def.nodes[node_id]
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
        await _record_attempt(ctx, record, run_id=run_id)
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
        await _record_attempt(ctx, record, run_id=run_id)

    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
    )
    return result.answer


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
    state and `produced_by` history, which only `_drive_scope`'s own replay
    holds (§12.1: nothing kept between calls). So this hands the raw
    decision to `_drive_scope` as `pending_decision`; `_advance_gate` applies it
    at exactly the point it is reached, with the same state it would use
    to check whether the gate is even still awaiting this decider.

    `decide()` (a `person` decider's own hand-off, below) hands `_advance_gate`
    a differently-shaped payload through the same channel — the middle
    element of the 3-tuple tags which shape it is (`"agent"` here), so a
    gate that turns out to actually be awaiting the OTHER kind never
    misreads one payload's fields as the other's.

    If this call turns out not to actually correspond to what the gate is
    currently awaiting (a stale hand-off, a second `report()` for the same
    decider, wrong node), `_advance_gate` simply never consumes the
    decision and `_drive_scope` returns the gate's actual current answer instead
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
    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
        pending_decision=(node_id, "agent", output),
    )
    return result.answer


def _value_matches_answer_type(value: Any, answer_type: str) -> bool:
    """`decide(..., value=...)`'s own runtime check that a submitted
    answer is shaped like `kind: INPUT`'s own `answer_type` declares
    (§7.6) — the same §2.1 type vocabulary `parse_type` already
    structures for a declared path's static type, applied here to one
    live value instead.

    Best-effort for `map<*>`/`profile:*` (accepts any mapping — this
    format has no runtime JSON Schema validator for a profile's own
    shape, and building one is out of scope for this work package); every
    other primitive is checked exactly, failing closed on anything else.
    """
    return _value_matches_type(value, parse_type(answer_type))


def _value_matches_type(value: Any, type_: Type) -> bool:
    if isinstance(type_, TString):
        return isinstance(value, str)
    if isinstance(type_, TInteger):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(type_, TNumber):
        return isinstance(value, int | float) and not isinstance(value, bool)
    if isinstance(type_, TBoolean):
        return isinstance(value, bool)
    if isinstance(type_, TAny):
        return True
    if isinstance(type_, TEnum):
        return value in type_.members
    if isinstance(type_, TList):
        return isinstance(value, list) and all(
            _value_matches_type(item, type_.item) for item in value
        )
    if isinstance(type_, TMap | TProfile):
        return isinstance(value, Mapping)
    return False


async def decide(
    process: Process,
    run_id: str,
    scope: str,
    gate_id: str,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    verdict: Verdict | None = None,
    value: Any = None,
    note: str | None = None,
    subject: str,
) -> NextAnswer:
    """§12.1: `decide(run, scope, gate, verdict, note)` — records a
    person's decision (identity from the caller) and continues driving
    forward.

    §10.1: "...or accepts any decision, it asks the host's `PolicyPort`" —
    checked before recording, the same as `_advance_step`'s STEP dispatch
    and `_advance_gate`'s agent-decider vote. Which permission: if this
    decision satisfies a declared `person`-kind decider at its rightful
    sequence position, that decider's own `permission` (§7.6: `person: {
    permission: <host permission> }`); otherwise (no deciders declared, or
    every declared decider already answered INDETERMINATE) the gate's own
    `permission` (D13's fallback, §7.6: "the gate stays open for a person
    with the gate's permission"). A `person` decider declared with `role`
    instead of `permission` is refused outright — `PolicyPort.authorize()`
    has no way to check a role, only an opaque permission string, and
    nothing here invents one.

    Fault 1 (WP-03a): this used to compute "which decider slot am I
    satisfying" itself, from `len(get_attempts(...))` — the gate's TOTAL
    attempt count across every PAST visit, not this specific, still-open
    visit's own. A gate looped back on DENY (§7.6's own worked example)
    and decided a second time overshot `len(node.deciders)` the moment the
    store held even one attempt from the FIRST visit, and silently fell
    through to the D13 gate-level-permission branch — refusing a real
    person decider's own, correctly-permissioned decision. The correct
    "which visit, which decider slot" answer needs exactly the replay
    `_advance_gate` already does (D20/D21/D22's own baseline discipline),
    so — mirroring `_report_gate_decision`'s own `pending_decision` shape
    for the `agent` case — this hands the raw verdict to `_drive_scope`
    and lets `_advance_gate` apply it at the point its own already-correct
    replay actually reaches it, rather than recomputing that position here
    a second, differently-shaped, and wrong way.

    `kind: INPUT` (D26/D41, WP-05 Part 1): a person decider answers with
    `value` instead of `verdict` — `decide(..., value=<matching
    answer_type>)`. `value` is checked against the gate's own
    `answer_type` (§7.6) before being handed to `_drive_scope`, the same
    "checked before recording" discipline §10.1 already applies to a
    verdict's own permission check. Which of `verdict`/`value` is
    required is decided by this gate's own `kind`, not by caller choice —
    the wrong one for this gate's `kind` is refused outright rather than
    silently ignored or silently accepted alongside the right one.
    """
    scope_def = _resolve_scope(process, scope, ctx.registry)
    node = scope_def.nodes[gate_id]
    if not isinstance(node, GateNode):
        raise EngineRefusal(
            f"decide() called for {gate_id!r}, which is not a GATE node"
        )

    payload: Mapping[str, Any]
    if node.kind == "INPUT":
        if verdict is not None:
            raise EngineRefusal(
                f"decide() called for {gate_id!r} (kind INPUT) with a "
                "`verdict` — INPUT gates are answered with `value`, not "
                "decided with a Verdict (§7.6)"
            )
        if value is None:
            raise EngineRefusal(
                f"decide() called for {gate_id!r} (kind INPUT) with no `value`"
            )
        assert node.answer_type is not None  # V9 requires it for kind: INPUT
        if not _value_matches_answer_type(value, node.answer_type):
            raise EngineRefusal(
                f"decide() called for {gate_id!r}: value {value!r} does not "
                f"match this gate's own answer_type {node.answer_type!r}"
            )
        payload = {"value": value, "subject": subject}
    else:
        if verdict is None:
            raise EngineRefusal(
                f"decide() called for {gate_id!r} (kind {node.kind}) with no `verdict`"
            )
        if value is not None:
            raise EngineRefusal(
                f"decide() called for {gate_id!r} (kind {node.kind}) with a "
                "`value` — only an INPUT gate is answered that way (§7.6)"
            )
        payload = {"verdict": verdict, "note": note, "subject": subject}

    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
        pending_decision=(gate_id, "person", payload),
    )
    return result.answer


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
    scope_def = _resolve_scope(process, scope, ctx.registry)
    node = scope_def.nodes[node_id]
    if not isinstance(node, StepNode):
        raise EngineRefusal(f"skip() called for {node_id!r}, which is not a STEP node")
    if scope_def.skip_policy != "ADVISORY":
        raise EngineRefusal(
            f"process {process.header.id!r} has skip_policy "
            f"{scope_def.skip_policy!r} — steps cannot be skipped (§6)"
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
    await _record_attempt(ctx, record, run_id=run_id)
    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
    )
    return result.answer


@dataclass(frozen=True)
class HeartbeatAnswer:
    """§12.3's `ClaimsPort.renew` exposed as a public call (D37, D42;
    WP-05 Part 2) — deliberately not a `NextAnswer`: nothing about the
    run's own position changes, only a claim's own lease, so there is no
    `kind`/`scope`/`ending` to report, only whether the renewal itself
    succeeded."""

    status: ClaimStatus
    says: str


async def heartbeat(
    process: Process,
    run_id: str,
    scope: str,
    node_id: str,
    ctx: EngineContext,
) -> HeartbeatAnswer:
    """§12.3: "A running step renews its lease" — the public call that
    was missing (D37, WP-03a): `ClaimsPort.renew` has been fully built and
    unit-tested since WP-02, but nothing in `next`/`report`/`decide`/
    `skip` (§12.1) ever let an in-flight caller invoke it, so a claim's
    lease could only ever grow as long as a host set `lease_seconds` up
    front — no way for a genuinely still-running `MUTATION`/`SIDE_EFFECT`
    step to extend it while real work is still in progress.

    Resolves the SAME `AttemptKey` `_claim_if_effectful` would use to
    claim this exact dispatch — mirroring `report()`'s own `len(attempts)
    + 1` shape (not `_advance_step`'s baseline-relative one; the two are
    always equal, since `len(all attempts) == baseline + len(this visit's
    own attempts)` by construction) — without replaying the whole run via
    `_drive_scope` first, the same "trust the caller's own (scope, node)"
    discipline `report()` already uses. The `Claim` passed to `renew` is
    necessarily a fresh, best-effort description (`claimed_by:
    ctx.identity`, a current `claimed_at`/`expires_at`) — this engine
    holds nothing in memory between calls (§12.1) and has no `get` on
    `ClaimsPort` to read one back, so it cannot know the TRUE original
    claim's own timestamps; a conforming `ClaimsPort.renew` implementation
    is authoritative on its own stored claim and only reads `key`/
    `claimed_by` off the argument to decide whether this caller still
    holds it (see `StubClaimsAdapter.renew`'s own docstring, D42).

    Refuses (`EngineRefusal`, propagating as a bare exception — the same
    "checked before doing anything" shape `skip()`'s own early checks
    already use) for a node that is not a `STEP`, or whose Tool's own
    `effect` is `QUERY` — §12.3's claim/lease guard exists only for
    `MUTATION`/`SIDE_EFFECT` steps, so there is nothing to renew for
    anything else.
    """
    scope_def = _resolve_scope(process, scope, ctx.registry)
    node = scope_def.nodes[node_id]
    if not isinstance(node, StepNode):
        raise EngineRefusal(
            f"heartbeat() called for {node_id!r}, which is not a STEP node"
        )
    tool = _resolve_tool(node.tool, ctx.registry)
    if tool.effect not in ("MUTATION", "SIDE_EFFECT"):
        raise EngineRefusal(
            f"heartbeat() called for {node_id!r}, whose tool "
            f"{tool.header.id!r} declares effect: {tool.effect} — §12.3's "
            "claim/lease guard only applies to MUTATION/SIDE_EFFECT steps, "
            "so there is no claim to renew"
        )
    attempts = await ctx.records.get_attempts(
        run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
    )
    key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=len(attempts) + 1)
    now = time.time()
    claim = Claim(key=key, claimed_by=ctx.identity, claimed_at=now, expires_at=now)
    result = await ctx.claims.renew(
        claim,
        lease_seconds=ctx.lease_seconds,
        platform_id=ctx.platform_id,
        run_id=run_id,
    )
    if result.status is not ClaimStatus.GRANTED:
        return HeartbeatAnswer(
            status=result.status,
            says=result.note
            or f"heartbeat() for {node_id!r} could not renew its claim.",
        )
    return HeartbeatAnswer(status=result.status, says=f"Lease for {node_id!r} renewed.")


# --------------------------------------------------------------------------- driving --


async def _drive_scope(
    process: Process,
    scope_def: _ScopeDef,
    run_id: str,
    scope: str,
    ctx: EngineContext,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    *,
    depth: int = 0,
    pending_decision: tuple[str, str, Mapping[str, Any]] | None = None,
    initial_state: Mapping[str, Any] | None = None,
    initial_produced_by: Mapping[str, str] | None = None,
    require_permission: bool = True,
    extra_namespaces: Mapping[str, Any] | None = None,
) -> _DriveResult:
    """Drives one scope level — the top-level run (`depth == 0`) or a
    nested `PROCESS`-mechanism call (§9, delegated from
    `_advance_process_call`) — forward from its own `scope_def.start`.

    `report()`/`decide()`/`skip()` always restart THIS function from
    `depth=0` at `scope.split("/")[0]` regardless of how deeply nested
    the node they just recorded an attempt for was — replay naturally
    re-descends (`_advance_step`'s `PROCESS`-mechanism branch,
    `_advance_process_call`) into whichever nested scope is still open
    and continues it from there. There is deliberately no separate
    "resume the child, then cascade the parent forward" path: delegating
    into a child scope and "the child already finished, keep going" are
    the same code, read from the same already-durable attempt records
    (§12.1: "nothing is held in memory between calls").

    A `PARALLEL` branch (WP-03 Part 1, D46) is driven through this SAME
    function too, but it is not a fresh scope's own beginning the way a
    `PROCESS` call's child is: `initial_state`/`initial_produced_by` seed
    it from the parent's own CURRENT values (spec §2.2's `state.<channel>`
    is one process-wide namespace — a branch is not isolated the way a
    `FOR_EACH` item is, §7.5), and `require_permission=False` skips the
    `depth == 0` permission gate below, since a branch has no `permission`
    of its own to check separately (it shares the parent run's own, already
    checked once at the true top level).

    A `FOR_EACH` item (WP-03 Part 2, D47) is driven through this SAME
    function too, the same way — but §7.5's own "isolated scope" wording
    means its `initial_state`/`initial_produced_by` are READ-ONLY seeds
    (nothing about an item's OWN writes threads to the NEXT item or folds
    back into the parent automatically the way a `PARALLEL` branch's do —
    `_advance_for_each` never reads `drive_result.produced_by`, and only
    `collect`'s own explicit mapping reaches the parent's real state).
    `extra_namespaces` (`{"item": {"value": ..., "index": ...}}`) exposes
    the current element to every node inside the item's own scope, the
    same generic top-level-namespace mechanism `compose.*` (D45) already
    proved works with zero special-casing in `evaluate()`.
    """
    if depth == 0 and require_permission:
        if process.permission is None:
            return _DriveResult(
                answer=_forbidden(
                    process,
                    "this process declares no `permission` — refusing to start (D14).",
                )
            )
        decision = await ctx.policy.authorize(
            process.permission,
            identity=ctx.identity,
            platform_id=ctx.platform_id,
            run_id=run_id,
        )
        if decision.verdict is not Verdict.PERMIT:
            return _DriveResult(
                answer=_forbidden(process, decision.rationale or "permission refused")
            )

    state: dict[str, Any] = (
        dict(initial_state)
        if initial_state is not None
        else {
            name: (channel.default if channel.has_default else None)
            for name, channel in scope_def.state.items()
        }
    )
    steps: dict[str, Any] = {}
    node_id = scope_def.start

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
    produced_by: dict[str, str] = (
        dict(initial_produced_by) if initial_produced_by is not None else {}
    )

    try:
        while True:
            if node_id not in scope_def.nodes:
                return _DriveResult(
                    answer=_ending_answer(scope_def.endings, node_id),
                    final_state=state,
                    produced_by=dict(produced_by),
                )

            node = scope_def.nodes[node_id]
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
                **(extra_namespaces or {}),
            }

            if isinstance(node, StepNode):
                advance = await _advance_step(
                    process,
                    scope_def,
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                    depth,
                )
            elif isinstance(node, RouteNode):
                advance = await _advance_route(
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
            elif isinstance(node, GateNode):
                advance = await _advance_gate(
                    process,
                    scope_def,
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
                        (pending_decision[1], pending_decision[2])
                        if pending_decision is not None
                        and pending_decision[0] == node_id
                        else None
                    ),
                    produced_by=produced_by,
                )
                if advance.took_loop:
                    gate_loop_taken[node_id] = gate_loop_taken.get(node_id, 0) + 1
            elif isinstance(node, ParallelNode):
                advance = await _advance_parallel(
                    process,
                    scope_def,
                    node,
                    node_id,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                    depth,
                    produced_by,
                )
            elif isinstance(node, JoinNode):
                advance = await _advance_join(
                    process,
                    scope_def,
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                    depth,
                    produced_by,
                )
            elif isinstance(node, ForEachNode):
                advance = await _advance_for_each(
                    process,
                    scope_def,
                    node,
                    node_id,
                    visit_attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                    depth,
                    produced_by,
                )
            else:
                raise EngineRefusal(
                    f"node {node_id!r} is a {type(node).__name__} node — unrecognised "
                    "by this engine's dispatch table."
                )

            if advance.answer is not None:
                return _DriveResult(answer=advance.answer)

            state = advance.state if advance.state is not None else state
            if advance.state is not None and isinstance(node, StepNode):
                identity = _producer_identity(advance.performed_by)
                if identity is not None:
                    for path in node.out.values():
                        produced_by[path] = identity
            if advance.produced_by:
                produced_by.update(advance.produced_by)
            steps[node_id] = (
                advance.step_record
                if advance.step_record is not None
                else steps.get(node_id)
            )
            # This visit is done — the next time (if ever) this same node_id
            # comes up in this call, it is a genuinely new visit. Advance the
            # baseline by exactly what THIS visit consumed (D20), not by
            # however many attempts the store now holds in total — those two
            # only coincide when nothing later in a multi-node loop body has
            # already recorded a future revisit's own attempts.
            if advance.visit_attempts_used is not None:
                visit_baseline[node_id] = baseline + advance.visit_attempts_used
            else:
                refreshed = await ctx.records.get_attempts(
                    run_id, scope, node_id, platform_id=ctx.platform_id, run_id=run_id
                )
                visit_baseline[node_id] = len(refreshed)
            node_id = advance.next_node_id  # type: ignore[assignment]
    except EngineRefusal as exc:
        return _DriveResult(
            answer=NextAnswer(
                kind=AnswerKind.ENDED, says=str(exc), ending="FAILED", outcome="FAILURE"
            )
        )


@dataclass
class _Advance:
    answer: NextAnswer | None = None
    next_node_id: str | None = None
    state: dict[str, Any] | None = None
    step_record: Mapping[str, Any] | None = None
    took_loop: bool = False
    performed_by: str | None = None
    """Who/what wrote `state` on a successful STEP — `_drive_scope` uses this to
    build `produced_by` (§7.6's "no deciding on your own work" needs to
    know which identity produced each reviewed state path, not just which
    Tool ran)."""
    visit_attempts_used: int | None = None
    """How many attempts, counting from this node's own visit baseline,
    this resolution actually consumed — `_drive_scope` advances
    `visit_baseline` by exactly this many, not by "however many attempts
    now exist in the store." A STEP or GATE revisited via a loop whose
    body spans more than one hand-off (D20) can otherwise have attempts
    belonging to a LATER, not-yet-reached revisit already sitting in the
    store by the time this one is walked — jumping the baseline straight
    to the store's total silently treats those as already consumed,
    stranding the run on the first node of the loop body forever. `None`
    (ROUTE, and the hand-off case, where nothing is consumed this call)
    keeps the old "however many attempts now exist" behaviour, which is
    exactly right there: a ROUTE's own visit is always exactly one
    attempt, and a hand-off records nothing yet to bump past."""
    produced_by: Mapping[str, str] | None = None
    """WP-03 Part 1 (D46): a `PARALLEL`/`JOIN` resolution's own folded
    `produced_by` (from `_drive_parallel_branches`, itself folded from each
    branch's own `_DriveResult.produced_by`) — merged into `_drive_scope`'s
    OWN tracking regardless of node type, unlike `performed_by` above
    (STEP-only, since only a STEP's own `out:` mapping names which paths
    it wrote)."""


def _resolve_tool(ref: str, registry: Registry) -> Tool:
    tool = registry.resolve("TOOL", ref)
    assert isinstance(tool, Tool)  # V2 already guarantees this resolves
    return tool


@dataclass(frozen=True)
class _ScopeDef:
    """The structural definition-of-record for one level of a run's scope
    tree (§9.3: "every answer names the scope and definition it belongs
    to, at any depth") — resolvable without any run-state or attempt
    replay, unlike `_drive_scope`'s own recursive descent (which
    additionally needs run-state to resolve a child's own inputs)."""

    nodes: Mapping[str, Node]
    start: str
    state: Mapping[str, StateChannel]
    endings: Mapping[str, Ending]
    skip_policy: str


def _scope_def_for_process(process: Process) -> _ScopeDef:
    return _ScopeDef(
        nodes=process.nodes,
        start=process.start,
        state=process.state,
        endings=process.endings,
        skip_policy=process.skip_policy,
    )


def _scope_def_for_mechanism(
    mechanism: Mechanism, parent: _ScopeDef, registry: Registry
) -> tuple[_ScopeDef, Process | None]:
    """§9's two call forms: a `ref` names an independently governed
    Process with its own `skip_policy` (checked separately, at the
    delegation site, from its own `.permission` — D14); an anonymous
    `process:` (D18) declares none of its own — it is fused into the
    parent Tool's already-checked dispatch permission, so it inherits
    the parent scope's `skip_policy` instead. Returns the ref'd child
    `Process` too (or `None` for inline), since the caller needs it
    separately for the permission check this function does not do."""
    if mechanism.ref is not None:
        child = registry.resolve("PROCESS", mechanism.ref)
        assert isinstance(child, Process)  # V2 already guarantees this resolves
        return _scope_def_for_process(child), child
    assert mechanism.process is not None  # V1: exactly one of ref/process (D18)
    inline = mechanism.process
    return (
        _ScopeDef(
            nodes=inline.nodes,
            start=inline.start,
            state=inline.state,
            endings=inline.endings,
            skip_policy=parent.skip_policy,
        ),
        None,
    )


def _resolve_scope(process: Process, scope: str, registry: Registry) -> _ScopeDef:
    """Walks a scope string structurally — following `mechanism.process`/
    `.ref` at each `PROCESS`-mechanism STEP a segment after the first
    names as having delegated one level deeper — to find which
    `_ScopeDef` governs it. Used by `report()`/`decide()`/`skip()` to
    resolve a (possibly nested) target node before recording an attempt;
    `_drive_scope`'s own descent needs run-state as well, so it computes
    each child's `_ScopeDef` inline via `_scope_def_for_mechanism` rather
    than calling this.

    WP-03 Part 1 (D46): a `PARALLEL` branch's own segment
    (`<parallel-node-id>.branch[<index>]`) is checked first, since it is
    never a real key in `scope_def.nodes` — a branch shares the PARENT
    level's own node map (not a separately-versioned Process the way a
    `PROCESS` call's child is, §9 vs this), so descending into one only
    ever changes `start`, never `nodes`/`state`/`endings`. WP-03 Part 2
    (D47): a `FOR_EACH` item's own segment (`<for-each-node-id>.item[<index>]`)
    is the same shape — `index` selects nothing structural here (every
    item shares the SAME `do` node id), it only distinguishes the scope
    STRING for addressing."""
    scope_def = _scope_def_for_process(process)
    for segment in scope.split("/")[1:]:
        branch_match = _BRANCH_SCOPE_SEGMENT_RE.match(segment)
        if branch_match is not None:
            parallel_node = scope_def.nodes.get(branch_match.group("node"))
            if not isinstance(parallel_node, ParallelNode):
                raise EngineRefusal(
                    f"scope segment {segment!r} does not name a PARALLEL node "
                    "in its own level"
                )
            index = int(branch_match.group("index"))
            if index >= len(parallel_node.branches):
                raise EngineRefusal(
                    f"scope segment {segment!r}: branch index out of range"
                )
            scope_def = replace(scope_def, start=parallel_node.branches[index])
            continue
        item_match = _FOR_EACH_ITEM_SCOPE_SEGMENT_RE.match(segment)
        if item_match is not None:
            for_each_node = scope_def.nodes.get(item_match.group("node"))
            if not isinstance(for_each_node, ForEachNode):
                raise EngineRefusal(
                    f"scope segment {segment!r} does not name a FOR_EACH node "
                    "in its own level"
                )
            scope_def = replace(scope_def, start=for_each_node.do)
            continue
        node = scope_def.nodes.get(segment)
        if not isinstance(node, StepNode):
            raise EngineRefusal(
                f"scope segment {segment!r} is not a STEP node in its own level"
            )
        tool = _resolve_tool(node.tool, registry)
        if tool.mechanism.kind != "PROCESS":
            raise EngineRefusal(
                f"scope segment {segment!r} does not call a process (§9)"
            )
        scope_def, _ = _scope_def_for_mechanism(tool.mechanism, scope_def, registry)
    return scope_def


def _resolve_call_inputs(
    mapping: Mapping[str, str | list[str]], run_state: Mapping[str, Any]
) -> dict[str, Any]:
    """§9.1: a process call's own `inputs:` mapping resolves the same way
    a Tool's own `in:` does (§7.1) — "the first present, non-empty value"
    of an ordered path list — reusing `steps.py`'s private helper the
    same way `_resolve_inputs_preview` already does."""
    from sulis_workflows.engine.steps import _first_present

    resolved: dict[str, Any] = {}
    for name, paths in mapping.items():
        path_list = [paths] if isinstance(paths, str) else list(paths)
        resolved[name] = _first_present(path_list, run_state)
    return resolved


@dataclass(frozen=True)
class _DriveResult:
    """`_drive_scope`'s own return — one layer richer than a bare
    `NextAnswer`: `_advance_process_call` needs a completed child scope's
    final accumulated state to evaluate `mechanism.result.outputs` paths
    (§9.1), which `NextAnswer` alone has nowhere to carry.

    `produced_by` (WP-03 Part 1, D46) is the same reason: a `PARALLEL`
    branch's own `_drive_scope` call builds its own local §7.6
    `produced_by` map for the STEPs it drives, which would otherwise be
    silently lost the moment that call returns — leaving a GATE reached
    AFTER the branch's own join with no way to tell it was reviewing a
    value THAT SAME identity had just produced inside the branch (a
    "no deciding on your own work" bypass, not merely a lost provenance
    detail). `_drive_parallel_branches` folds this back into the
    OUTER scope's own tracking exactly as it does `final_state`."""

    answer: NextAnswer
    final_state: Mapping[str, Any] | None = None
    produced_by: Mapping[str, str] | None = None


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


def _ending_answer(endings: Mapping[str, Ending], ending_id: str) -> NextAnswer:
    declared = endings.get(ending_id)
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


async def _claim_if_effectful(
    ctx: EngineContext,
    tool: Tool,
    key: AttemptKey,
    *,
    run_id: str,
    scope: str,
    node_id: str,
) -> _Advance | None:
    """D37: §12.3's claim/lease guard, shared by both a Tool's dispatch
    paths (inline `CODE` and a `TOOL_STEP` hand-off) since a hand-off IS
    this step's own dispatch, the same reasoning §10.1/D12's permission
    check already applies. A no-op for a `QUERY`-effect Tool (no claim
    needed). Returns a `STEP_RUNNING` `_Advance` if someone else already
    holds this claim, else `None` to let the caller proceed with its own
    dispatch."""
    if tool.effect not in ("MUTATION", "SIDE_EFFECT"):
        return None
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
                scope=scope,
            )
        )
    return None


async def _advance_step(
    process: Process,
    scope_def: _ScopeDef,
    node: StepNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
) -> _Advance:
    tool = _resolve_tool(node.tool, ctx.registry)
    # D20: `attempts` (sliced from this node's own visit baseline) may hold
    # more than this visit's own history if a later node in a multi-node
    # loop body already recorded a future revisit before this one was
    # walked — narrow to the earliest visit's own prefix before deciding
    # anything, so a stale or premature attempt is never mistaken for the
    # current one.
    attempts = _visit_prefix(attempts)
    retry_backoff_seconds: float | None = None

    if attempts:
        last = attempts[-1]
        if last.verdict == "SKIPPED":
            # §6: an ADVISORY skip() call already recorded this — proceed as
            # the step's own declared route says, without ever dispatching
            # the Tool or writing anything into state (there is no output).
            return _Advance(
                next_node_id=_success_target(node), visit_attempts_used=len(attempts)
            )
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
                # §7.1/§15: "backoff_seconds is the starting delay before
                # exponential backoff" — `attempts` already holds `len(attempts)`
                # TRANSIENT attempts, so this dispatch is retry number
                # `len(attempts)`; the delay doubles from `backoff_seconds`
                # on the first retry.
                base_backoff = (
                    retry.backoff_seconds
                    if retry and retry.backoff_seconds is not None
                    else fmt_defaults.RETRY_BACKOFF_SECONDS
                )
                retry_backoff_seconds = base_backoff * (2 ** (len(attempts) - 1))
            else:
                return _Advance(
                    next_node_id=_route_for_step_failure(node, last, tool),
                    visit_attempts_used=len(attempts),
                )
        elif outcome is StepOutcome.SUCCESS:
            new_state = apply_output(
                scope_def.state, run_state["state"], node.out, last.output or {}
            )
            return _Advance(
                next_node_id=_success_target(node),
                state=new_state,
                step_record={"output": last.output, "attempt": len(attempts)},
                performed_by=last.performed_by,
                visit_attempts_used=len(attempts),
            )
        elif outcome is StepOutcome.CONTROL_FAILED:
            if _repair_count(attempts) <= _repair_budget(node):
                pass  # fall through to dispatch another (repair) attempt below
            else:
                return _Advance(
                    next_node_id=_route_for_step_failure(node, last, tool),
                    visit_attempts_used=len(attempts),
                )
        elif outcome in (
            StepOutcome.CONTROLS_UNCHECKABLE,
            StepOutcome.FORBIDDEN,
            StepOutcome.PRECONDITION_FALSE,
            StepOutcome.NOT_DISPATCHABLE,
            StepOutcome.INPUT_UNRESOLVED,
        ):
            return _Advance(
                next_node_id=_route_for_step_failure(node, last, tool),
                visit_attempts_used=len(attempts),
            )
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

    if tool.mechanism.kind == "PROCESS":
        # §9: a nested call — `ref`'d or inline (D18) — is neither a CODE
        # dispatch nor a hand-off to the caller's own agent session; the
        # engine drives it itself, recursively. This only fires on a
        # fresh visit or a retry/repair fallthrough (never on plain
        # replay of an already-recorded SUCCESS/failure, handled above).
        return await _advance_process_call(
            process,
            scope_def,
            node,
            node_id,
            tool,
            attempts,
            baseline,
            run_state,
            run_id,
            scope,
            ctx,
            depth,
        )

    if tool.mechanism.kind == "TOOL":
        # D34/D45: TOOL-composite has no `ref` to hand off, and its own
        # `composes` children would simply never be dispatched by the
        # generic `not in ("CODE", "EXTERNAL")` branch just below, which
        # is written for a SKILL hand-off's own shape — so it is driven
        # here, the same way a `PROCESS`-mechanism call is (above), rather
        # than falling into that branch. This only fires on a fresh visit
        # or a retry/repair fallthrough (never on plain replay of an
        # already-recorded SUCCESS/failure, handled above).
        return await _advance_compose(
            process,
            scope_def,
            node,
            node_id,
            tool,
            attempts,
            baseline,
            run_state,
            run_id,
            scope,
            ctx,
            depth,
        )

    key = AttemptKey(
        run=run_id, scope=scope, node=node_id, attempt=baseline + len(attempts) + 1
    )

    if tool.mechanism.kind not in ("CODE", "EXTERNAL"):
        # §10.1/D12: permission is checked before ANY dispatch, hand-off
        # included — a `TOOL_STEP` hand-off IS the dispatch for a `SKILL`
        # Tool (the caller's agent session performs it next), so
        # refusing this check here rather than only inside `attempt_step`
        # (CODE/EXTERNAL only) closes a gap where a permission-less or
        # refused SKILL Tool was previously handed off uncontrolled.
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
                scope_def,
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
                depth,
                performed_by=f"AGENT:{tool.mechanism.ref}::{ctx.identity}",
            )

        # D37: §12.3's claim/lease guard ("before a MUTATION or SIDE_EFFECT
        # step runs, the engine writes an in-progress claim") is the
        # dispatch-time at-most-once protection this format has — and a
        # `TOOL_STEP` hand-off IS this step's own dispatch, exactly the
        # principle §10.1/D12's permission check (just above) already
        # applies here. Before this fix, `ctx.claims.acquire` was only
        # ever called on the CODE-only path below, so a hand-off
        # MUTATION/SIDE_EFFECT Tool — the case a real-world side effect
        # performed by an external agent most needs at-most-once
        # protection for — had none at all: a second caller racing in
        # during the hand-off got a fresh `TOOL_STEP` instead of being
        # told `STEP_RUNNING`.
        claim_advance = await _claim_if_effectful(
            ctx, tool, key, run_id=run_id, scope=scope, node_id=node_id
        )
        if claim_advance is not None:
            return claim_advance

        resolved_inputs, _missing = _resolve_inputs_preview(node, tool, run_state)
        return _Advance(
            answer=NextAnswer(
                kind=AnswerKind.TOOL_STEP,
                says=f"Waiting on {node.tool} to run.",
                node_id=node_id,
                scope=scope,
                resolved_inputs=resolved_inputs,
                # §12.1: "TOOL_STEP ... resolved inputs, instructions ref,
                # controls" — `instructions_ref` is the mechanism's own
                # `ref` (§4.3: "a skill document" for SKILL), previously
                # only reachable by the caller looking the Tool up itself
                # via `node.tool` and the registry, not carried on the answer.
                instructions_ref=tool.mechanism.ref,
                controls=tuple({"kind": c.kind, "ref": c.ref} for c in tool.controls),
                skippable=_is_skippable(scope_def, node),
            )
        )

    claim_advance = await _claim_if_effectful(
        ctx, tool, key, run_id=run_id, scope=scope, node_id=node_id
    )
    if claim_advance is not None:
        return claim_advance

    if retry_backoff_seconds is not None:
        await asyncio.sleep(retry_backoff_seconds)

    result = await attempt_step(
        node,
        tool,
        run_state,
        identity=ctx.identity,
        platform_id=ctx.platform_id,
        run_id=run_id,
        policy=ctx.policy,
        code_tool=ctx.code_tool,
        external_tool=ctx.external_tool,
        registry=ctx.registry,
    )
    return await _record_step_result(
        process,
        scope_def,
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
        depth,
        performed_by=f"{tool.mechanism.kind}:{tool.mechanism.ref}",
    )


async def _record_step_result(
    process: Process,
    scope_def: _ScopeDef,
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
    depth: int,
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
    new_state: dict[str, Any] | None = None
    if result.outcome is StepOutcome.SUCCESS:
        try:
            new_state = apply_output(
                scope_def.state, run_state["state"], node.out, result.output or {}
            )
        except ReducerMismatch as exc:
            # §2.3: "a write that does not match the channel type is refused
            # and recorded as a failed attempt" — checked BEFORE recording
            # (D19), so the durable record itself reflects the refusal
            # rather than a SUCCESS record a state write then breaks.
            result = StepAttemptResult(
                outcome=StepOutcome.STATE_MISMATCH,
                rationale=str(exc),
            )

    key = AttemptKey(
        run=run_id, scope=scope, node=node_id, attempt=baseline + len(attempts) + 1
    )
    # §12.2: "inputs used" — the same resolved inputs `_advance_step` already
    # computed (and, for a hand-off, shows the caller via `resolved_inputs`)
    # to decide whether this dispatch could even be attempted. `run_state`
    # is unchanged since then (this function is called synchronously within
    # the same `_advance_step`/`_record_step_result` pass, before any state
    # write from THIS attempt is applied), so recomputing here is exact, not
    # a guess.
    resolved_inputs, _ = _resolve_inputs_preview(node, tool, run_state)
    record = AttemptRecord(
        key=key,
        inputs=resolved_inputs,
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
    await _record_attempt(ctx, record, run_id=run_id)

    if result.outcome is StepOutcome.SUCCESS:
        return _Advance(
            next_node_id=_success_target(node),
            state=new_state,
            performed_by=performed_by,
            visit_attempts_used=len(attempts) + 1,
        )
    if result.outcome is StepOutcome.ERROR and result.error_class == "TRANSIENT":
        retry = node.retry
        max_retries = (
            retry.max if retry and retry.max is not None else fmt_defaults.RETRY_MAX
        )
        if len(attempts) + 1 <= max_retries:
            return await _advance_step(
                process,
                scope_def,
                node,
                node_id,
                attempts + [record],
                baseline,
                run_state,
                run_id,
                scope,
                ctx,
                depth,
            )
    if result.outcome is StepOutcome.CONTROL_FAILED and _repair_count(
        attempts + [record]
    ) <= _repair_budget(node):
        return await _advance_step(
            process,
            scope_def,
            node,
            node_id,
            attempts + [record],
            baseline,
            run_state,
            run_id,
            scope,
            ctx,
            depth,
        )
    return _Advance(
        next_node_id=_route_for_step_failure(node, record, tool),
        visit_attempts_used=len(attempts) + 1,
    )


def _parse_step_outcome(value: str) -> StepOutcome | None:
    try:
        return StepOutcome(value)
    except ValueError:
        return None


def _visit_prefix(attempts: list[AttemptRecord]) -> list[AttemptRecord]:
    """D20: the prefix of `attempts` (already sliced from this node's own
    visit baseline) belonging to the EARLIEST visit that has not yet been
    resolved — up to and including the first attempt that ends a visit
    one way or another. Anything after that prefix belongs to a revisit
    this replay pass has not reached yet.

    Only `TRANSIENT` `ERROR` and `CONTROL_FAILED` ever continue a visit
    (§12.4, §10.2 step 5 — retry and repair); every other outcome,
    `SKIPPED`, and an unparseable verdict all end it. This mirrors
    `_advance_step`'s own retry/repair fall-through exactly, so it never
    needs its own view of the repair/retry budget: once a budget is
    genuinely exhausted, `_advance_step` stops dispatching, so there is
    simply no further attempt in the store to over-include."""
    for index, record in enumerate(attempts):
        if record.verdict == "SKIPPED":
            return attempts[: index + 1]
        outcome = (
            _parse_step_outcome(record.verdict) if record.verdict is not None else None
        )
        if outcome is StepOutcome.ERROR:
            error_class = (record.output or {}).get("error_class", "PERMANENT")
            if error_class == "TRANSIENT":
                continue
            return attempts[: index + 1]
        if outcome is StepOutcome.CONTROL_FAILED:
            continue
        return attempts[: index + 1]
    return attempts


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


def _is_skippable(scope_def: _ScopeDef, node: StepNode) -> bool:
    """§6: structurally eligible for `skip()` — `ADVISORY` skip policy,
    TRIVIAL criticality. Does not check `skip_permission`/authorization;
    `skip()` itself enforces that at the point of the actual call, the
    same way a GATE's `on` routes are shown regardless of whether this
    particular caller holds the gate's permission."""
    criticality = node.criticality or fmt_defaults.STEP_CRITICALITY
    return scope_def.skip_policy == "ADVISORY" and criticality == "TRIVIAL"


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
    if outcome_value == StepOutcome.DEPTH_EXHAUSTED.value:
        target = node.on_depth_exhausted or RouteTarget(
            end=fmt_defaults.ON_DEPTH_EXHAUSTED
        )
        return _resolve_route_target(target)
    raise EngineRefusal(
        f"step {node.id!r}: no route declared for outcome {outcome_value!r}"
    )


# -------------------------------------------------------------------- calling a process --


async def _advance_process_call(
    process: Process,
    scope_def: _ScopeDef,
    node: StepNode,
    node_id: str,
    tool: Tool,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
) -> _Advance:
    """§9: dispatches a `PROCESS`-mechanism STEP — `ref`'d or inline
    (D18) — by recursively driving a child scope one level deeper
    (`_drive_scope`), then translating the child's ending into this
    STEP's own output via `mechanism.result` (§9.1) and routing that
    translated output through the SAME `check_controls`/
    `_record_step_result` machinery a CODE dispatch uses — a control
    failure or a repair on a process call means the same thing it does
    on any other Tool, so nothing here special-cases it.

    A repair (or retry) fallthrough re-enters this function and
    re-delegates into the same child scope; since the child's own
    attempts are already durable and complete, that re-delegation just
    idempotently re-observes the same already-ended child result rather
    than re-running anything — a known, deliberately unengineered nuance
    (see the run record for this change) rather than a real retry of the
    child's own internal logic.
    """
    mechanism = tool.mechanism
    if mechanism.path is not None:
        raise EngineRefusal(
            f"process call {node_id!r} declares `path` — overriding the "
            "child's first route (§9.1) is not yet supported by this engine."
        )

    max_depth = (
        process.defaults.max_depth
        if process.defaults is not None and process.defaults.max_depth is not None
        else fmt_defaults.MAX_DEPTH
    )
    if depth + 1 > max_depth:
        depth_result = StepAttemptResult(
            outcome=StepOutcome.DEPTH_EXHAUSTED,
            rationale=(
                f"call chain depth {depth + 1} exceeds the limit of {max_depth} (§9.2)"
            ),
        )
        return await _record_step_result(
            process,
            scope_def,
            node,
            node_id,
            tool,
            depth_result,
            attempts,
            baseline,
            run_state,
            run_id,
            scope,
            ctx,
            depth,
            performed_by="ENGINE:depth-limit",
        )

    if mechanism.ref is not None:
        child_process = ctx.registry.resolve("PROCESS", mechanism.ref)
        assert isinstance(child_process, Process)  # V2 already guarantees this resolves
        precheck: StepAttemptResult | None
        if child_process.permission is None:
            precheck = StepAttemptResult(
                outcome=StepOutcome.FORBIDDEN,
                rationale=(
                    f"process {mechanism.ref!r} declares no `permission` — "
                    "refusing to call it rather than skip the check (§10.1, D14)."
                ),
            )
        else:
            decision = await ctx.policy.authorize(
                child_process.permission,
                identity=ctx.identity,
                platform_id=ctx.platform_id,
                run_id=run_id,
            )
            precheck = (
                None
                if decision.verdict is Verdict.PERMIT
                else StepAttemptResult(
                    outcome=StepOutcome.FORBIDDEN,
                    rationale=decision.rationale or "called process permission refused",
                )
            )
        if precheck is not None:
            return await _record_step_result(
                process,
                scope_def,
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
                depth,
                performed_by=f"PROCESS:{mechanism.ref}",
            )

    child_scope_def, _ = _scope_def_for_mechanism(mechanism, scope_def, ctx.registry)
    child_scope = f"{scope}/{node_id}"
    child_inputs = _resolve_call_inputs(mechanism.inputs, run_state)
    drive_result = await _drive_scope(
        process,
        child_scope_def,
        run_id,
        child_scope,
        ctx,
        child_inputs,
        run_state["host"],
        depth=depth + 1,
    )
    if drive_result.answer.kind is not AnswerKind.ENDED:
        return _Advance(answer=drive_result.answer)

    output: dict[str, Any] = {}
    if mechanism.result is not None:
        endings_map = mechanism.result.endings
        child_ending = drive_result.answer.ending
        if child_ending is None or child_ending not in endings_map:
            raise EngineRefusal(
                f"process call {node_id!r}: child ending {child_ending!r} has no "
                "result.endings mapping (V10 should have refused this at validation time)"
            )
        # D40: the mapped ending is always synthesised under the literal
        # key "ending" below — if the calling STEP's own `out:` never
        # captures it into state, the child's own ending (which can be a
        # failure or a stop, not just a success) is unreadable by anything
        # downstream, silently masked as this step's own plain SUCCESS the
        # moment its controls (if any) pass regardless. V10 should have
        # refused this at validation time; this is the runtime half.
        if "ending" not in node.out:
            raise EngineRefusal(
                f"step {node_id!r} calls a process but its `out:` mapping does not "
                "capture the result's `ending` into state (V10 should have refused "
                "this at validation time)"
            )
        final_run_state = {"state": drive_result.final_state or {}}
        output = {
            name: _evaluate(path, final_run_state)
            for name, path in mechanism.result.outputs.items()
        }
        output["ending"] = endings_map[child_ending]

    from sulis_workflows.engine.controls import check_controls

    controls_result = await check_controls(
        tool,
        output,
        registry=ctx.registry,
        code_tool=ctx.code_tool,
        platform_id=ctx.platform_id,
        run_id=run_id,
    )
    if not controls_result.checkable:
        call_outcome = StepOutcome.CONTROLS_UNCHECKABLE
    elif controls_result.all_passed:
        call_outcome = StepOutcome.SUCCESS
    else:
        call_outcome = StepOutcome.CONTROL_FAILED
    call_result = StepAttemptResult(
        outcome=call_outcome,
        output=output if call_outcome is StepOutcome.SUCCESS else None,
        controls=controls_result,
    )
    return await _record_step_result(
        process,
        scope_def,
        node,
        node_id,
        tool,
        call_result,
        attempts,
        baseline,
        run_state,
        run_id,
        scope,
        ctx,
        depth,
        performed_by=f"PROCESS:{mechanism.ref or 'inline'}",
    )


# ---------------------------------------------------------------------- composing tools --

_COMPOSE_CHILD_NODE_ID_RE = re.compile(r"^(?P<outer>.+)\.compose\[(?P<index>\d+)\]$")


def _apply_compose_output(
    item: ComposeItem, child_output: Mapping[str, Any], compose_state: dict[str, Any]
) -> None:
    """`ComposeItem.output` maps ITS OWN Tool's output fields into
    `compose.<path>` — the composite call's own private, ordered scratch
    space (WP-04 Part 2, D45), mirroring exactly how a STEP's own `out:`
    maps a Tool's output into `state.*` (`apply_output`, `engine/state.py`)
    — simpler, since `compose.*` has no declared channels or reducers of
    its own: a bare, last-write-wins write, silently skipping a field the
    child's own output didn't actually produce (the same leniency
    `apply_output` already has for `out:`, spec §7.1)."""
    for tool_field, target_path in item.output.items():
        if not target_path.startswith("compose."):
            continue  # schema/V4-equivalent already restricts targets to compose.* (D45)
        if tool_field not in child_output:
            continue
        compose_state[target_path[len("compose.") :]] = child_output[tool_field]


async def _advance_compose(
    process: Process,
    scope_def: _ScopeDef,
    node: StepNode,
    node_id: str,
    tool: Tool,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
) -> _Advance:
    """WP-04 Part 2 (D45): dispatches a `TOOL`-composite STEP — walks
    `composes` in declared order, each child dispatched through the SAME
    per-mechanism-kind dispatch every other Tool already has (`attempt_step`
    for `CODE`/`EXTERNAL`; the identical permission-check-then-hand-off
    shape `_advance_step`'s own `SKILL` branch already has for `SKILL`) —
    reused, not duplicated. `compose.*` (a new, composite-call-scoped
    run-state namespace, parallel to `steps.*`) accumulates each earlier
    child's own mapped `output`, readable by a LATER child's own `inputs:`
    mapping alongside the composite Tool's own `inputs.*`/`state.*`/`host.*`.

    Mirrors `_advance_process_call`'s own "nothing recorded at the OUTER
    node until the whole call finally resolves" discipline (§9's own
    nested-scope pattern, applied one level down without an actual nested
    SCOPE — see below): each child's own durable attempt is recorded under
    its own synthetic node id (`f"{node_id}.compose[{i}]"`, the SAME scope
    as the composite STEP itself, not a deeper one — a documented departure
    from this work package's own design draft, decided here because
    composed children are a flat, fixed-length sequence, not an independent
    node graph with its own `start`/`nodes`/`endings`; a nested scope's
    real purpose elsewhere is representing exactly that, which `composes`
    never has). Only ever recorded ON SUCCESS (`_report_compose_child`'s
    own docstring): a FAILING child's own dispatch is never durably keyed,
    so a later composite-level TRANSIENT retry (the OUTER node's own
    existing retry logic, unchanged) re-dispatches the failing child fresh
    rather than replaying a stale failure forever, while every
    already-succeeded child is skipped via its own durable record.

    Refuses (`EngineRefusal`) a composed child whose own `mechanism.kind`
    is anything but `CODE`/`EXTERNAL`/`SKILL` — `PROCESS` recursion and
    nested `TOOL`-composite children are both out of this pass's own scope
    (the latter named explicitly in the WP-04 design document itself); V2
    already refuses a nested-`TOOL` child at validation time, this is the
    runtime half.
    """
    mechanism = tool.mechanism
    compose_state: dict[str, Any] = {}
    compose_run_state = {**run_state, "compose": compose_state}

    for i, item in enumerate(mechanism.composes):
        child_tool = _resolve_tool(item.tool, ctx.registry)
        if child_tool.mechanism.kind not in ("CODE", "EXTERNAL", "SKILL"):
            raise EngineRefusal(
                f"step {node_id!r}: composed child {i} ({item.tool!r}) declares "
                f"mechanism.kind: {child_tool.mechanism.kind} — only CODE, "
                "EXTERNAL and SKILL composed children are supported by this "
                "engine (spec §4.3, WP-04 Part 2)"
            )
        child_node_id = f"{node_id}.compose[{i}]"

        child_attempts = await ctx.records.get_attempts(
            run_id, scope, child_node_id, platform_id=ctx.platform_id, run_id=run_id
        )
        if child_attempts:
            # Only ever durably recorded on success (see above) — replay
            # reapplies the same already-known output and moves on,
            # without re-dispatching a child that already ran.
            _apply_compose_output(item, child_attempts[-1].output or {}, compose_state)
            continue

        child_key = AttemptKey(run=run_id, scope=scope, node=child_node_id, attempt=1)

        if child_tool.mechanism.kind == "SKILL":
            # §10.1/D12, mirroring `_advance_step`'s own SKILL branch: a
            # composed child's own permission is checked before ANY
            # dispatch, hand-off included — composing does not bypass
            # governance for the Tools it composes.
            permission_rationale: str | None
            if child_tool.permission is None:
                permission_rationale = (
                    f"Tool {child_tool.header.id!r} declares no `permission` — "
                    "refusing to dispatch rather than skip the check (spec "
                    "§10.1, D12)."
                )
            else:
                decision = await ctx.policy.authorize(
                    child_tool.permission,
                    identity=ctx.identity,
                    platform_id=ctx.platform_id,
                    run_id=run_id,
                )
                permission_rationale = (
                    None
                    if decision.verdict is Verdict.PERMIT
                    else (decision.rationale or "composed child permission refused")
                )
            if permission_rationale is not None:
                forbidden_result = StepAttemptResult(
                    outcome=StepOutcome.FORBIDDEN, rationale=permission_rationale
                )
                return await _record_step_result(
                    process,
                    scope_def,
                    node,
                    node_id,
                    tool,
                    forbidden_result,
                    attempts,
                    baseline,
                    run_state,
                    run_id,
                    scope,
                    ctx,
                    depth,
                    performed_by=f"AGENT:{child_tool.mechanism.ref}::{ctx.identity}",
                )
            claim_advance = await _claim_if_effectful(
                ctx,
                child_tool,
                child_key,
                run_id=run_id,
                scope=scope,
                node_id=child_node_id,
            )
            if claim_advance is not None:
                return claim_advance
            resolved_inputs, _missing = _resolve_inputs_preview(
                StepNode(id=child_node_id, tool=item.tool, in_=item.inputs, out={}),
                child_tool,
                compose_run_state,
            )
            return _Advance(
                answer=NextAnswer(
                    kind=AnswerKind.TOOL_STEP,
                    says=f"Waiting on {item.tool} to run.",
                    node_id=child_node_id,
                    scope=scope,
                    resolved_inputs=resolved_inputs,
                    instructions_ref=child_tool.mechanism.ref,
                    controls=tuple(
                        {"kind": c.kind, "ref": c.ref} for c in child_tool.controls
                    ),
                    skippable=False,
                )
            )

        # CODE / EXTERNAL — dispatched synchronously, the exact shape a
        # top-level STEP's own inline dispatch already has (`attempt_step`,
        # WP-04 Part 1's own reuse of it for EXTERNAL applies identically
        # here, one level down).
        claim_advance = await _claim_if_effectful(
            ctx,
            child_tool,
            child_key,
            run_id=run_id,
            scope=scope,
            node_id=child_node_id,
        )
        if claim_advance is not None:
            return claim_advance
        child_step_node = StepNode(
            id=child_node_id, tool=item.tool, in_=item.inputs, out={}
        )
        child_result = await attempt_step(
            child_step_node,
            child_tool,
            compose_run_state,
            identity=ctx.identity,
            platform_id=ctx.platform_id,
            run_id=run_id,
            policy=ctx.policy,
            code_tool=ctx.code_tool,
            external_tool=ctx.external_tool,
            registry=ctx.registry,
        )
        if child_result.outcome is not StepOutcome.SUCCESS:
            # A4: never durably recorded (see above) — the composite's own
            # ONE attempt, at the OUTER node, carries this failure, routed
            # through the calling STEP's own on_error/on_control_fail by
            # the same `_record_step_result`/`_route_for_step_failure`
            # machinery any other dispatch failure already uses.
            return await _record_step_result(
                process,
                scope_def,
                node,
                node_id,
                tool,
                child_result,
                attempts,
                baseline,
                run_state,
                run_id,
                scope,
                ctx,
                depth,
                performed_by=f"{child_tool.mechanism.kind}:{item.tool}",
            )
        child_record = AttemptRecord(
            key=child_key,
            inputs={},
            output=dict(child_result.output or {}),
            control_results=(
                [
                    {
                        "control": o.control.ref,
                        "passed": o.passed,
                        "findings": list(o.findings),
                    }
                    for o in child_result.controls.outcomes
                ]
                if child_result.controls
                else []
            ),
            verdict=child_result.outcome.value,
            performed_by=f"{child_tool.mechanism.kind}:{item.tool}",
            started_at=_now(),
            ended_at=_now(),
        )
        await _record_attempt(ctx, child_record, run_id=run_id)
        _apply_compose_output(item, child_result.output or {}, compose_state)

    # Every child succeeded — fill the composite's own top-level `output:`
    # the same way §9.1's own `mechanism.result.outputs` already fills a
    # `PROCESS` call's output (`_advance_process_call`, above): reusing
    # `CallResult`'s own shape verbatim rather than inventing a
    # composite-only field, since the shape (`{name: path}`) is identical
    # either way and `mechanism.result` is not schema-gated to `PROCESS`
    # mechanisms only.
    output: dict[str, Any] = {}
    if mechanism.result is not None:
        output = {
            name: _evaluate(path, compose_run_state)
            for name, path in mechanism.result.outputs.items()
        }
    success_result = StepAttemptResult(outcome=StepOutcome.SUCCESS, output=output)
    return await _record_step_result(
        process,
        scope_def,
        node,
        node_id,
        tool,
        success_result,
        attempts,
        baseline,
        run_state,
        run_id,
        scope,
        ctx,
        depth,
        performed_by="TOOL:compose",
    )


async def _report_compose_child(
    process: Process,
    run_id: str,
    scope: str,
    outer_node_id: str,
    child_index: int,
    ctx: EngineContext,
    *,
    inputs: Mapping[str, Any],
    host_inputs: Mapping[str, Any],
    output: Mapping[str, Any] | None,
    error_code: str | None,
) -> NextAnswer:
    """Completes a composed `SKILL` child's own `TOOL_STEP` hand-off
    (WP-04 Part 2, D45).

    On SUCCESS: records the child's own durable attempt (keyed by the
    synthetic `f"{outer_node_id}.compose[{i}]"` node id, same scope as
    `_advance_compose` already uses) and resumes driving from the top;
    replay naturally re-enters `_advance_compose` for the OUTER node,
    reads this child's own now-durable attempt, and continues to the
    next child (or finishes).

    On FAILURE (an `error_code`, or the reported output's own controls
    not passing): NEVER durably records the child's own attempt (the
    same "only success is durable" discipline `_advance_compose` itself
    keeps, for the identical reason — a later composite-level retry must
    re-dispatch this exact child fresh, not replay a stale failure) —
    instead routes the failure to the OUTER node directly, via the same
    `_record_step_result` a synchronous `CODE`/`EXTERNAL` child failure
    already uses in `_advance_compose`, returning its own answer without
    restarting the top-level replay at all (nothing was recorded that
    replay would need to re-discover).
    """
    scope_def = _resolve_scope(process, scope, ctx.registry)
    outer_node = scope_def.nodes.get(outer_node_id)
    if not isinstance(outer_node, StepNode):
        raise EngineRefusal(
            f"report() called for a composed child of {outer_node_id!r}, which "
            "is not a STEP node"
        )
    outer_tool = _resolve_tool(outer_node.tool, ctx.registry)
    if outer_tool.mechanism.kind != "TOOL" or not (
        0 <= child_index < len(outer_tool.mechanism.composes)
    ):
        raise EngineRefusal(
            f"report() called for {outer_node_id!r}.compose[{child_index}], "
            "which does not name a composed child of a TOOL-composite Tool"
        )
    item = outer_tool.mechanism.composes[child_index]
    child_tool = _resolve_tool(item.tool, ctx.registry)
    child_node_id = f"{outer_node_id}.compose[{child_index}]"
    child_key = AttemptKey(run=run_id, scope=scope, node=child_node_id, attempt=1)

    if error_code is not None:
        child_result = StepAttemptResult(
            outcome=StepOutcome.ERROR,
            error_code=error_code,
            error_class=_classify_error(child_tool, error_code),
            rationale=f"composed child {child_index} reported error {error_code!r}",
        )
    else:
        from sulis_workflows.engine.controls import check_controls

        controls_result = await check_controls(
            child_tool,
            output or {},
            registry=ctx.registry,
            code_tool=ctx.code_tool,
            platform_id=ctx.platform_id,
            run_id=run_id,
        )
        if not controls_result.checkable:
            child_outcome = StepOutcome.CONTROLS_UNCHECKABLE
        elif controls_result.all_passed:
            child_outcome = StepOutcome.SUCCESS
        else:
            child_outcome = StepOutcome.CONTROL_FAILED
        child_result = StepAttemptResult(
            outcome=child_outcome, output=output, controls=controls_result
        )

    if child_result.outcome is StepOutcome.SUCCESS:
        record = AttemptRecord(
            key=child_key,
            inputs={},
            output=dict(child_result.output or {}),
            control_results=(
                [
                    {
                        "control": o.control.ref,
                        "passed": o.passed,
                        "findings": list(o.findings),
                    }
                    for o in child_result.controls.outcomes
                ]
                if child_result.controls
                else []
            ),
            verdict=child_result.outcome.value,
            performed_by=f"AGENT:{child_tool.mechanism.ref}::{ctx.identity}",
            started_at=_now(),
            ended_at=_now(),
        )
        await _record_attempt(ctx, record, run_id=run_id)
        top_scope = scope.split("/")[0]
        result = await _drive_scope(
            process,
            _scope_def_for_process(process),
            run_id,
            top_scope,
            ctx,
            inputs,
            host_inputs,
        )
        return result.answer

    # FAILURE — never recorded at the child's own key (see docstring);
    # route it straight to the OUTER node's own ONE attempt instead.
    # `attempts`/`baseline`/`run_state`/`depth` for the OUTER node are
    # necessarily approximated here rather than replayed (report() is not
    # itself a replay walk) — the same simplification `report()`'s own
    # plain STEP branch already makes for its own `AttemptRecord.inputs`
    # (always `{}`, a known, accepted limitation; see the run record for
    # this decision). This is safe because a `TOOL`-composite STEP never
    # itself recurses into another process call (composed `PROCESS`
    # children are refused, above), so `depth` has no observable effect
    # here.
    outer_attempts = await ctx.records.get_attempts(
        run_id, scope, outer_node_id, platform_id=ctx.platform_id, run_id=run_id
    )
    outer_run_state: dict[str, Any] = {
        "inputs": inputs,
        "host": host_inputs,
        "state": {},
        "steps": {},
    }
    outer_advance = await _record_step_result(
        process,
        scope_def,
        outer_node,
        outer_node_id,
        outer_tool,
        child_result,
        outer_attempts,
        0,
        outer_run_state,
        run_id,
        scope,
        ctx,
        0,
        performed_by=f"AGENT:{child_tool.mechanism.ref}::{ctx.identity}",
    )
    if outer_advance.answer is not None:
        return outer_advance.answer
    # `_record_step_result` returned a routing decision (`next_node_id`),
    # not a terminal answer — e.g. a CONTROL_FAILED repair budget not yet
    # exhausted recursed back into `_advance_step` itself, which (since
    # nothing was actually recorded for a compose-child failure) always
    # resolves synchronously; restarting the top-level replay reaches the
    # identical conclusion the same way any other STEP's own eventual
    # routing decision would.
    top_scope = scope.split("/")[0]
    result = await _drive_scope(
        process,
        _scope_def_for_process(process),
        run_id,
        top_scope,
        ctx,
        inputs,
        host_inputs,
    )
    return result.answer


# ---------------------------------------------------------------------- parallel and join --

_BRANCH_SCOPE_SEGMENT_RE = re.compile(r"^(?P<node>.+)\.branch\[(?P<index>\d+)\]$")


async def _drive_parallel_branches(
    process: Process,
    scope_def: _ScopeDef,
    parallel_node: ParallelNode,
    parallel_node_id: str,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
    outer_produced_by: Mapping[str, str],
) -> tuple[NextAnswer | None, dict[str, Any], list[tuple[str, str]], dict[str, str]]:
    """Drives every one of `parallel_node.branches`, in declared order,
    each as its own nested scope (`{scope}/{parallel_node_id}.branch[{i}]`)
    — the same §9.3 nested-scope pattern a `PROCESS` call's child already
    uses, applied one level down, but sharing `scope_def.nodes` (not a
    separate node map: a branch is not an independently-versioned Process,
    just `branches`'s own node ids inside THIS process's `nodes:`).

    Shared by `_advance_parallel` (reached first, on every replay, since
    the walk always passes through the `PARALLEL` node before its own
    `JOIN`) and `_advance_join` (which independently re-derives the same
    result to get each branch's own final `outcome` — cheap, since every
    branch's own attempts are already durable; `_drive_scope` itself does
    no new work on a branch already replayed to its own ending).

    Returns `(pending, folded_state, endings, folded_produced_by)`:
      - `pending`: the first branch's own not-yet-`ENDED` answer, the
        moment one is found, bubbled up untouched — `None` once every
        branch has reached `ENDED`. Never short-circuited early even once
        a policy is ALREADY decided by fewer than every branch finishing
        (D46: this engine has no primitive to cancel a still-open branch's
        own pending hand-off, so "wait for all of them, always" is the
        only construct built from what already exists — see D46 for the
        spec's own ambiguous "or can no longer be met" wording, §7.4).
      - `folded_state`: each branch's own state writes, threaded through
        SEQUENTIALLY in branch order — spec §2.2 has ONE process-wide
        `state` namespace (a branch is not isolated the way a `FOR_EACH`
        item is, §7.5's own explicit "isolated scope" wording, absent
        from §7.4) — so a later branch's own STEPs, and everything after
        the `JOIN`, read whatever an earlier branch already wrote.
      - `endings`: `(ending_id, outcome)` per branch, in declared order —
        `_advance_join`'s own input to `policy`.
      - `folded_produced_by`: §7.6's own "no deciding on your own work"
        provenance, threaded and folded the same way `folded_state` is —
        without this, a GATE reached after the join could not tell it was
        reviewing a value the SAME identity had just produced inside a
        branch (D46).
    """
    state = dict(run_state["state"])
    produced_by = dict(outer_produced_by)
    endings: list[tuple[str, str]] = []
    for index, branch_start in enumerate(parallel_node.branches):
        branch_scope_def = replace(scope_def, start=branch_start)
        branch_scope = f"{scope}/{parallel_node_id}.branch[{index}]"
        drive_result = await _drive_scope(
            process,
            branch_scope_def,
            run_id,
            branch_scope,
            ctx,
            run_state["inputs"],
            run_state["host"],
            depth=depth,
            initial_state=state,
            initial_produced_by=produced_by,
            require_permission=False,
        )
        if drive_result.answer.kind is not AnswerKind.ENDED:
            return drive_result.answer, state, endings, produced_by
        state = (
            dict(drive_result.final_state)
            if drive_result.final_state is not None
            else state
        )
        if drive_result.produced_by:
            produced_by.update(drive_result.produced_by)
        assert drive_result.answer.ending is not None
        assert drive_result.answer.outcome is not None
        endings.append((drive_result.answer.ending, drive_result.answer.outcome))
    return None, state, endings, produced_by


async def _advance_parallel(
    process: Process,
    scope_def: _ScopeDef,
    node: ParallelNode,
    node_id: str,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
    outer_produced_by: Mapping[str, str],
) -> _Advance:
    """§7.4: "every branch start is handed out." A `PARALLEL` node has no
    `next`/`end` of its own — it always routes to `node.join` once every
    branch has reached `ENDED`; `_advance_join`, reached next in this SAME
    walk (the walk always passes through here first), evaluates the
    policy and does the actual routing. Nothing is durably recorded at
    THIS node's own key — like `ROUTE`'s non-looping case, it is a pure,
    replay-cheap fan-out with nothing of its own worth an attempt record
    (unlike `ROUTE`, it has no loop-budget count to make durable either)."""
    (
        pending,
        folded_state,
        _endings,
        folded_produced_by,
    ) = await _drive_parallel_branches(
        process,
        scope_def,
        node,
        node_id,
        run_state,
        run_id,
        scope,
        ctx,
        depth,
        outer_produced_by,
    )
    if pending is not None:
        return _Advance(answer=pending)
    return _Advance(
        next_node_id=node.join,
        state=folded_state,
        produced_by=folded_produced_by,
        visit_attempts_used=0,
    )


def _find_parallel_for_join(
    scope_def: _ScopeDef, join_node_id: str
) -> tuple[str, ParallelNode]:
    for candidate_id, candidate in scope_def.nodes.items():
        if isinstance(candidate, ParallelNode) and candidate.join == join_node_id:
            return candidate_id, candidate
    raise EngineRefusal(
        f"join {join_node_id!r} is not reachable from exactly one PARALLEL's own "
        "`join` field (V11 should have refused this at validation time)"
    )


def _join_success_target(node: JoinNode) -> str:
    if node.next is not None:
        return node.next
    if node.end is not None:
        return node.end
    raise EngineRefusal(
        f"join {node.id!r} satisfied with no `next` or `end` declared (V7 gap)"
    )


async def _advance_join(
    process: Process,
    scope_def: _ScopeDef,
    node: JoinNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
    outer_produced_by: Mapping[str, str],
) -> _Advance:
    """§7.4: "the join runs exactly once, when its policy is met" —
    evaluated only once `_drive_parallel_branches` confirms every one of
    the corresponding `PARALLEL`'s own branches has reached `ENDED`
    (structurally guaranteed by the time this node is ever reached, since
    `_advance_parallel` gates on exactly that before ever routing here —
    the `pending` branch below is defensive only, for a hand-built,
    validation-bypassed `Process`). `policy` (default `ALL_SUCCESS`, spec
    §15) is evaluated fresh on every visit — deterministic, from
    already-durable branch endings, so recomputing costs nothing and needs
    no replay-branch reconstruction the way `ROUTE`'s own loop-budget
    count does; the durable attempt written here (once, D46) is for
    §12.2's own "every attempt of every node" auditability, not because
    a later replay needs to read it back to resolve anything."""
    parallel_node_id, parallel_node = _find_parallel_for_join(scope_def, node_id)
    pending, folded_state, endings, folded_produced_by = await _drive_parallel_branches(
        process,
        scope_def,
        parallel_node,
        parallel_node_id,
        run_state,
        run_id,
        scope,
        ctx,
        depth,
        outer_produced_by,
    )
    if pending is not None:
        return _Advance(answer=pending)

    policy = node.policy or fmt_defaults.JOIN_POLICY
    outcomes = [outcome for _, outcome in endings]
    if policy == "ALL_SUCCESS":
        satisfied = all(outcome == "SUCCESS" for outcome in outcomes)
    elif policy == "ANY_SUCCESS":
        satisfied = any(outcome == "SUCCESS" for outcome in outcomes)
    else:  # ALL_COMPLETE — every branch reached SOME ending, already guaranteed
        satisfied = True

    if not attempts:
        key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=baseline + 1)
        record = AttemptRecord(
            key=key,
            inputs={},
            output={
                "policy": policy,
                "branch_endings": [ending for ending, _ in endings],
                "branch_outcomes": outcomes,
                "satisfied": satisfied,
            },
            control_results=[],
            verdict="SATISFIED" if satisfied else "NOT_SATISFIED",
            performed_by="ENGINE:join",
            started_at=_now(),
            ended_at=_now(),
        )
        await _record_attempt(ctx, record, run_id=run_id)

    if satisfied:
        next_id = _join_success_target(node)
    elif node.on_join_failed is not None:
        next_id = _resolve_route_target(node.on_join_failed)
    else:
        next_id = fmt_defaults.ON_JOIN_FAILED

    return _Advance(
        next_node_id=next_id,
        state=folded_state,
        produced_by=folded_produced_by,
        visit_attempts_used=1,
    )


# ------------------------------------------------------------------------------ for each --

_FOR_EACH_ITEM_SCOPE_SEGMENT_RE = re.compile(r"^(?P<node>.+)\.item\[(?P<index>\d+)\]$")


def _for_each_success_target(node: ForEachNode) -> str:
    if node.next is not None:
        return node.next
    if node.end is not None:
        return node.end
    raise EngineRefusal(
        f"for_each {node.id!r} satisfied with no `next` or `end` declared (V7 gap)"
    )


def _apply_collect(
    state_channels: Mapping[str, StateChannel],
    current_state: Mapping[str, Any],
    collect: CollectSpec,
    drive_result: _DriveResult,
    node_id: str,
    index: int,
) -> dict[str, Any]:
    """`collect: { output, into }` gathers ONE item's own contribution
    into the parent's real state (the only channel back to the parent for
    an isolated `FOR_EACH` item, D47). `output: "ending"` is a reserved
    name — the item's own terminal ending id (`drive_result.answer.ending`),
    the same synthesised-under-the-literal-key convention `mechanism.
    result.outputs`'s own "ending" key already uses for a `PROCESS` call
    (§9.1, D40) — reused here rather than invented fresh, matching the
    real `examples/recursive-refinement/` fixture's own
    `collect: { output: ending, into: state.recurse_endings }`, which
    predates this decision and names no `state.ending` channel anywhere
    (confirmed: `output` is schema-typed as a bare string, not a
    `path_expr` the way `into` is — never meant to be a general path).
    Any other `output` name reads the item's own final `state.<output>`.

    Applied for EVERY item that reaches `ENDED`, regardless of its own
    outcome — the real fixture's own `join: ALL_COMPLETE` pairs `collect`
    with counting every item as done whether it succeeded or not, and a
    collected trail of what each item actually ended with is exactly the
    diagnostic value `ALL_COMPLETE` exists for.

    Reuses `apply_output` (the same reducer-application code a STEP's own
    `out:` mapping already uses) via a throwaway single-field mapping,
    rather than duplicating `_reduce`'s own reducer logic — but pre-wraps
    a non-list value in `[value]` before handing it to an `APPEND` target,
    since `apply_output`'s own `_reduce` extends a list (`base + value`)
    rather than appending one new element; collect's own job (accumulate
    ONE contribution per item into a growing list) needs the latter
    unless an item's own contribution is already a list of several values
    (spec §7.4's own worked example, `output: insights` — already
    `list<profile:insight@1>`-typed — concatenates as-is, unwrapped)."""
    value: Any
    if collect.output == "ending":
        value = drive_result.answer.ending
    else:
        value = (drive_result.final_state or {}).get(collect.output)

    if not collect.into.startswith("state."):
        return dict(current_state)  # V4-equivalent restriction: a future
        # validator pass (WP-03 Part 3) should refuse this at validation
        # time; silently skipped here, the same defence-in-depth leniency
        # `_apply_compose_output` (D45) already has for its own compose.*
        # restriction.
    channel_name = collect.into[len("state.") :]
    channel = state_channels.get(channel_name)
    if (
        channel is not None
        and channel.reducer == "APPEND"
        and not isinstance(value, list)
    ):
        value = [value]

    try:
        return apply_output(
            state_channels,
            current_state,
            {"__collect__": collect.into},
            {"__collect__": value},
        )
    except ReducerMismatch as exc:
        raise EngineRefusal(
            f"for_each {node_id!r}: item {index} collect write refused ({exc})"
        ) from exc


async def _advance_for_each(
    process: Process,
    scope_def: _ScopeDef,
    node: ForEachNode,
    node_id: str,
    attempts: list[AttemptRecord],
    baseline: int,
    run_state: Mapping[str, Any],
    run_id: str,
    scope: str,
    ctx: EngineContext,
    depth: int,
    outer_produced_by: Mapping[str, str],
) -> _Advance:
    """§7.5: each element of `over` runs `do` in its own ISOLATED scope
    (`{scope}/{node_id}.item[{index}]`) — unlike a `PARALLEL` branch
    (D46), an item's own `state`/`produced_by` writes do NOT thread to the
    next item or fold back into the parent; `initial_state`/
    `initial_produced_by` are READ-ONLY seeds (real use needs to read
    prior process context, the same reason a branch does) and
    `drive_result.produced_by` is deliberately never read here (D47).
    `collect` is the ONLY channel back to the parent: reuses `apply_output`
    verbatim (the same reducer-application code a STEP's own `out:`
    mapping already uses) against the item's own final `state`, keeping
    `collect.output`'s bare-string shape (schema: `type: string`, not a
    `path_expr` the way `into` is) consistent with reading a bare channel
    name out of the item's own isolated state, not a general path.

    The current element is exposed two ways (D47): seeded into the item's
    own isolated `state.<as>` (`node.as_`'s target — a REAL, already-
    declared state channel, per the already-committed
    `examples/recursive-refinement/` fixture's own `state.child`/
    `state.recommendation` usage, predating this decision), and ALSO as
    `item.value`/`item.index` via `extra_namespaces` — a bonus convenience
    an author can use INSTEAD OF declaring an `as:` channel, e.g. for the
    index. Both read the exact SAME underlying value; neither is required
    over the other.

    `max_concurrency` (default 1, spec §15) throttles only what THIS visit
    is willing to newly open — never a concurrency primitive the engine
    itself enforces (there is nothing here to enforce it against): an
    item with ANY durable attempt at its own `do` node is always
    (re-)driven regardless of budget; an item with none is opened only
    while `open_count` is under budget. `join` (a bare policy string, no
    separate node the way `PARALLEL`'s `join` is) is evaluated the same
    way `_advance_join` evaluates `policy` — but `ForEachNode` has no
    `on_join_failed` field at all (schema-confirmed): an unsatisfied
    policy always falls through to the engine's own default (`end:
    FAILED`, spec §15), with no per-node override possible."""
    over_value = _evaluate(node.over, run_state)
    if not isinstance(over_value, list):
        raise EngineRefusal(
            f"for_each {node_id!r}: `over` ({node.over!r}) did not resolve to a "
            "list (V12 should have refused this at validation time)"
        )

    max_concurrency = node.max_concurrency or fmt_defaults.FOR_EACH_CONCURRENCY
    parent_state = run_state["state"]
    collected_state = dict(parent_state)
    endings: list[tuple[str, str]] = []
    pending: NextAnswer | None = None
    open_count = 0

    for index, item_value in enumerate(over_value):
        item_scope = f"{scope}/{node_id}.item[{index}]"
        item_do_attempts = await ctx.records.get_attempts(
            run_id, item_scope, node.do, platform_id=ctx.platform_id, run_id=run_id
        )
        if not item_do_attempts and open_count >= max_concurrency:
            continue  # held back by max_concurrency -- never touched this call

        item_scope_def = replace(scope_def, start=node.do)
        drive_result = await _drive_scope(
            process,
            item_scope_def,
            run_id,
            item_scope,
            ctx,
            run_state["inputs"],
            run_state["host"],
            depth=depth,
            initial_state={**parent_state, node.as_: item_value},
            initial_produced_by=outer_produced_by,
            require_permission=False,
            extra_namespaces={"item": {"value": item_value, "index": index}},
        )
        if drive_result.answer.kind is not AnswerKind.ENDED:
            open_count += 1
            if pending is None:
                pending = drive_result.answer
            continue

        assert drive_result.answer.ending is not None
        assert drive_result.answer.outcome is not None
        endings.append((drive_result.answer.ending, drive_result.answer.outcome))
        if node.collect is not None:
            collected_state = _apply_collect(
                scope_def.state,
                collected_state,
                node.collect,
                drive_result,
                node_id,
                index,
            )

    if pending is not None:
        return _Advance(answer=pending)

    policy = node.join or fmt_defaults.JOIN_POLICY
    outcomes = [outcome for _, outcome in endings]
    if policy == "ALL_SUCCESS":
        satisfied = all(outcome == "SUCCESS" for outcome in outcomes)
    elif policy == "ANY_SUCCESS":
        satisfied = any(outcome == "SUCCESS" for outcome in outcomes)
    else:  # ALL_COMPLETE -- every item reached SOME ending, already guaranteed
        satisfied = True

    if not attempts:
        key = AttemptKey(run=run_id, scope=scope, node=node_id, attempt=baseline + 1)
        record = AttemptRecord(
            key=key,
            inputs={},
            output={
                "policy": policy,
                "item_endings": [ending for ending, _ in endings],
                "item_outcomes": outcomes,
                "satisfied": satisfied,
            },
            control_results=[],
            verdict="SATISFIED" if satisfied else "NOT_SATISFIED",
            performed_by="ENGINE:for_each",
            started_at=_now(),
            ended_at=_now(),
        )
        await _record_attempt(ctx, record, run_id=run_id)

    if satisfied:
        next_id = _for_each_success_target(node)
    else:
        next_id = fmt_defaults.ON_JOIN_FAILED

    return _Advance(
        next_node_id=next_id,
        state=collected_state,
        visit_attempts_used=1,
    )


# ----------------------------------------------------------------------------- ROUTE --


async def _advance_route(
    process: Process,
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
        await _record_attempt(ctx, record, run_id=run_id)
        target = decision.target
    else:
        # D20-shaped gap, found pressure-testing the real grounded-inquiry
        # process (spec Appendix A) once its `after-interrogate` REVISED
        # loop had looped back more than once: `attempts` here is every
        # attempt from `baseline` onward this SAME walk has not yet
        # consumed, which holds more than one PAST visit's own record once
        # a loop has looped back more than once by the time this walk
        # catches up to it. Only the earliest of those (`attempts[0]`)
        # belongs to the visit being resolved right now; jumping straight
        # to the latest (the old `attempts[-1]`) replayed a LATER visit's
        # decision in its place, silently skipping every node the walk
        # should have passed through first (here, a genuine re-ask of
        # `interrogate`) and could apply the loop-budget check to a visit
        # whose state was never actually reached fresh.
        matched_index = (attempts[0].output or {}).get("matched_index")
        target = (
            RouteTarget(
                next=node.when[matched_index].next,
                end=node.when[matched_index].end,
                loop=node.when[matched_index].loop,
                # D38: this replay branch reconstructs `target` from the
                # matched `when` option's own fields on every call after the
                # one that first recorded this decision — `invalidates` was
                # dropped here (still read correctly on the fresh-evaluation
                # branch just above), the same "correct once, silently lost
                # on replay" shape D19/D27 already found and fixed elsewhere
                # in this file. Carried through now so a refusal (or, in
                # future, a real implementation) sees it consistently
                # regardless of which call first reaches this node.
                invalidates=node.when[matched_index].invalidates,
            )
            if matched_index is not None
            else node.otherwise
        )

    assert target is not None
    if target.invalidates:
        # D38: `invalidates` is accepted by the schema and model (spec §7.2)
        # but never read anywhere the engine resolves state — nothing marks
        # a channel invalid, and nothing checks for one. Appendix A's own
        # worked example does not declare it (checked directly against the
        # fixture, contradicting an unverified claim that had propagated
        # across earlier run records), and no fixture or test in this repo
        # exercises it, so refusing costs the real corpus nothing. Refusing
        # rather than silently no-op'ing it: a definition author who
        # declares `invalidates` is expressing an intent ("this ends a
        # prior channel's validity") that the engine would otherwise ignore
        # without telling them — the same "refuse cleanly rather than guess
        # or drop" precedent as D26/D27/D34. V18 refuses this at validation
        # time; this is the runtime half, in case validation is bypassed.
        raise EngineRefusal(
            f"route {node_id!r}: `invalidates` is declared but not "
            "implemented by this engine (D38) — remove it, or track the "
            "gap as a proposed spec change"
        )
    if target.loop is not None:
        if target.loop.counts == "FAILURES":
            # D33: unlike a GATE (DECIDED only ever carries PERMIT/DENY —
            # DENY unambiguously means ADR-028's own "check failed"), a
            # ROUTE's `when` branch is an arbitrary state expression with
            # no engine-visible "this is a failure" signal at all. Refusing
            # rather than guessing which branch "counts" — V8 already
            # refuses this at validation time; this is the runtime half,
            # in case validation is bypassed.
            raise EngineRefusal(
                f"route {node_id!r}: loop.counts: FAILURES is not supported for a "
                "ROUTE loop (D33) — only a GATE's DENY verdict is an unambiguous "
                "'because a check failed' signal; a ROUTE's `when` branch has none"
            )
        # `baseline` is exactly how many times this loop has been taken
        # before this occurrence: every route visit before the final one in
        # a loop's own visit sequence takes the loop by construction (a
        # visit that doesn't take it ends the sequence), and this function
        # always resolves exactly one visit's own attempt now
        # (`visit_attempts_used=1` below, matching `attempts[0]` above), so
        # `baseline` alone — not `baseline` plus any part of the unconsumed
        # slice — is the count taken strictly BEFORE this occurrence.
        budget_decision = check_loop_budget(
            target.loop,
            taken_count=baseline,
            process_default_budget=(
                process.defaults.loop_budget if process.defaults is not None else None
            ),
        )
        if budget_decision.outcome is LoopBudgetOutcome.EXHAUSTED:
            return _Advance(
                next_node_id=_resolve_route_target(budget_decision.on_exhausted),
                visit_attempts_used=1,
            )

    return _Advance(next_node_id=_resolve_route_target(target), visit_attempts_used=1)


# ------------------------------------------------------------------------------ GATE --


def _gate_visit_prefix(
    node: GateNode, attempts: list[AttemptRecord], *, person_required: bool
) -> list[AttemptRecord]:
    """D22: `_visit_prefix` (D20)'s counterpart for GATE nodes. `attempts`
    (already sliced from this node's own visit baseline) may hold more
    than one PAST resolution's own deciders once a gate loop has been
    taken more than once before a replay walk catches up to it — the same
    shape of gap D20/D21 fixed for STEP/ROUTE. Unlike those two, a GATE
    resolution's own attempt count varies (1 to `len(node.deciders)`,
    however many deciders were actually asked before one decided or every
    one answered `INDETERMINATE`), so there is no fixed-size prefix to
    take — this replays `resolve_gate` itself, one attempt at a time, and
    stops at the first prefix it calls `DECIDED`. If nothing in `attempts`
    ever decides it, the whole slice genuinely belongs to one still-open
    resolution (matches the existing NEEDS_*/PAUSED handling) and is
    returned unchanged.

    `resolve_gate`/`resolve_input_gate` are pure, so replaying either here
    costs nothing beyond a few extra calls over a small, bounded list (at
    most `len(node.deciders)` attempts belong to any one resolution).
    `kind: INPUT` (D26/D41) replays `resolve_input_gate` over
    `AnswerOutcome`s instead — the same prefix-search shape, a different
    outcome type."""
    for index in range(1, len(attempts) + 1):
        prefix = attempts[:index]
        if node.kind == "INPUT":
            answer_outcomes = [
                _answer_from_record(i, rec) for i, rec in enumerate(prefix)
            ]
            decision = resolve_input_gate(
                node, answer_outcomes, person_required=person_required
            )
        else:
            outcomes = [_outcome_from_record(i, rec) for i, rec in enumerate(prefix)]
            decision = resolve_gate(node, outcomes, person_required=person_required)
        if decision.resolution is GateResolution.DECIDED:
            return prefix
    return attempts


async def _advance_gate(
    process: Process,
    scope_def: _ScopeDef,
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
    pending_decision: tuple[str, Mapping[str, Any]] | None,
    produced_by: Mapping[str, str],
) -> _Advance:
    """`pending_decision`, when present, is `(kind, payload)` — `kind` is
    `"agent"` (a `report()`-completed `DECISION_STEP`, `payload` shaped
    like a Tool's own output: `verdict`/`evidence`/`rationale`) or
    `"person"` (a `decide()` call, `payload` shaped `verdict`/`note`/
    `subject` for an `APPROVAL` gate, or `value`/`subject` for a `kind:
    INPUT` one, per that gate's own `node.kind` — D26/D41). The two top-
    level kinds are never interchangeable — a gate that turns out to
    actually be awaiting the OTHER kind must never misread one payload's
    fields as the other's — so each consuming branch below checks its own
    `kind` before touching `payload` at all; a mismatched `pending_decision`
    is simply never consumed here, same as the established node-id
    mismatch case (`_report_gate_decision`'s own docstring)."""
    # D26/D41 (WP-05 Part 1): `kind: INPUT` is now executed — resolved via
    # `resolve_input_gate` (an `AnswerOutcome` sequence, `{ANSWERED,
    # INDETERMINATE}`) rather than `resolve_gate` (a `Verdict` sequence),
    # branched on below wherever the two kinds' own decision vocabulary
    # actually differs; everything else (deciders asked in order,
    # `person_required_when`, provenance recording) is shared.
    person_required = node.person_required_when is not None and bool(
        _evaluate(node.person_required_when, run_state)
    )
    # D22: `attempts` (sliced from this node's own visit baseline) may hold
    # more than one PAST resolution's own deciders if a GATE loop has been
    # taken more than once before a replay walk catches up to it — the
    # same class of gap D20/D21 fixed for STEP/ROUTE. Feeding all of them
    # into resolve_gate at once would silently merge two separate,
    # already-decided resolutions into one (using only the earliest
    # decider's verdict and never seeing the rest), rather than replaying
    # each resolution as its own. Narrow to the earliest resolution's own
    # prefix first.
    attempts = _gate_visit_prefix(node, attempts, person_required=person_required)
    if node.kind == "INPUT":
        answer_outcomes = [
            _answer_from_record(index, rec) for index, rec in enumerate(attempts)
        ]
        gate_decision = resolve_input_gate(
            node, answer_outcomes, person_required=person_required
        )
    else:
        outcomes = [
            _outcome_from_record(index, rec) for index, rec in enumerate(attempts)
        ]
        gate_decision = resolve_gate(node, outcomes, person_required=person_required)

    if gate_decision.resolution is GateResolution.DECIDED:
        # §7.6's `note_into`: what the decider wrote is the whole point of a
        # send-back — it is the instruction for the next attempt. Written into
        # state here, on the decision's own replay, so the step the run loops
        # back to reads it exactly like any other input (declared and unwritten,
        # a DENY sent work back with the reason silently dropped).
        decided_state = _state_with_note(scope_def, node, attempts, run_state)
        if node.kind == "INPUT":
            # D26/D41: `kind: INPUT` has no ADR-028 verdict at all — its
            # own decision vocabulary is `{ANSWERED, INDETERMINATE}`
            # (`resolve_input_gate`'s own), so the route key is always
            # `ANSWERED` and the decided value (not a `Verdict`) is
            # written to `answer_into` rather than `note_into`.
            answer_outcome = gate_decision.decided_by
            assert isinstance(
                answer_outcome, AnswerOutcome
            )  # DECIDED always carries one
            decided_state = _state_with_answer(
                scope_def,
                node,
                answer_outcome.value,
                decided_state if decided_state is not None else run_state["state"],
            )
            route_key = "ANSWERED"
        else:
            assert gate_decision.verdict is not None  # DECIDED always carries a verdict
            route_key = gate_decision.verdict.value
        target = node.on.get(route_key)
        if target is None:
            raise EngineRefusal(
                f"gate {node_id!r}: no route declared for verdict {route_key!r}"
            )
        if target.invalidates:
            # D38: same refusal as `_advance_route`'s — see that comment.
            # `node.on.get(...)` reads the static model directly every
            # call, so (unlike the ROUTE replay branch) no prerequisite
            # replay-drop fix was needed here for this check to be
            # consistent across calls.
            raise EngineRefusal(
                f"gate {node_id!r}: `invalidates` is declared but not "
                "implemented by this engine (D38) — remove it, or track "
                "the gap as a proposed spec change"
            )
        if target.loop is not None:
            # D33: §7.3/§15's `counts: FAILURES` ("only when taken because
            # a check failed") is unambiguous for a GATE: DECIDED only ever
            # carries PERMIT or DENY (never INDETERMINATE), and DENY is
            # ADR-028's own negative outcome — the "check failed" case a
            # `policy`/`agent`/`person` decider can produce. A take this
            # loop's own `counts` says shouldn't count skips the budget
            # check entirely, rather than being silently exhausted by a
            # failure count it was never supposed to be bound by.
            loop_counts = target.loop.counts or fmt_defaults.LOOP_COUNTS
            counts_this_take = (
                loop_counts != "FAILURES" or gate_decision.verdict is Verdict.DENY
            )
            if counts_this_take:
                budget_decision = check_loop_budget(
                    target.loop,
                    taken_count=prior_loop_takes,
                    process_default_budget=(
                        process.defaults.loop_budget
                        if process.defaults is not None
                        else None
                    ),
                )
                if budget_decision.outcome is LoopBudgetOutcome.EXHAUSTED:
                    return _Advance(
                        next_node_id=_resolve_route_target(
                            budget_decision.on_exhausted
                        ),
                        state=decided_state,
                        visit_attempts_used=len(attempts),
                    )
            return _Advance(
                next_node_id=_resolve_route_target(target),
                state=decided_state,
                took_loop=counts_this_take,
                visit_attempts_used=len(attempts),
            )
        return _Advance(
            next_node_id=_resolve_route_target(target),
            state=decided_state,
            visit_attempts_used=len(attempts),
        )

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
        if node.kind == "INPUT":
            # D26/D41: `PolicyPort.evaluate_policy` returns ADR-028's own
            # `Verdict` — nowhere to carry an `answer_type`-typed value.
            # A policy decider asked on an INPUT gate can therefore never
            # actually answer it; its own PERMIT/DENY/INDETERMINATE
            # verdict is recorded here for provenance only and always
            # treated as "did not answer" (WP-05 design, A2) — the next
            # decider is always asked next, exactly as an ordinary
            # INDETERMINATE outcome already is.
            record = AttemptRecord(
                key=key,
                inputs={},
                output={
                    "rationale": outcome.rationale,
                    "policy_verdict": outcome.verdict.value,
                },
                control_results=[],
                verdict="INDETERMINATE",
                performed_by=outcome.decided_by,
                started_at=_now(),
                ended_at=_now(),
            )
        else:
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
        await _record_attempt(ctx, record, run_id=run_id)
        return await _advance_gate(
            process,
            scope_def,
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

        if pending_decision is not None and pending_decision[0] == "agent":
            agent_output = pending_decision[1]
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
                    agent_output,
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
            if node.kind == "INPUT":
                # D26/D41: `decision@1`'s own profile (verdict/rationale/
                # evidence, checked by V9 for every gate regardless of
                # kind) has nowhere to carry an `answer_type`-typed value
                # either — the same gap named for policy deciders above.
                # Recorded for provenance, always "did not answer".
                record = AttemptRecord(
                    key=key,
                    inputs={},
                    output={
                        "evidence": list(outcome.evidence),
                        "rationale": outcome.rationale,
                        "agent_verdict": outcome.verdict.value,
                    },
                    control_results=[],
                    verdict="INDETERMINATE",
                    performed_by=outcome.decided_by,
                    started_at=_now(),
                    ended_at=_now(),
                )
            else:
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
            await _record_attempt(ctx, record, run_id=run_id)
            return await _advance_gate(
                process,
                scope_def,
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
                scope=scope,
                resolved_inputs={
                    "agent_tool": decider.ref,
                    "criteria": node.criteria,
                    "reviewing": list(node.reviewing),
                },
            )
        )

    if gate_decision.resolution is GateResolution.NEEDS_PERSON:
        assert gate_decision.next_decider_index is not None
        decider_index = gate_decision.next_decider_index
        decider = node.deciders[
            decider_index
        ]  # NEEDS_PERSON only ever names a `person` decider

        if pending_decision is not None and pending_decision[0] == "person":
            # Fault 1 (WP-03a): `decider_index` here comes from `resolve_gate`
            # over THIS visit's own, correctly-replayed `outcomes` (D22's own
            # `_gate_visit_prefix` truncation above already narrowed `attempts`
            # to just this resolution) — never from a bare count of every
            # attempt the gate has ever had. That was the bug: a second visit
            # after a DENY loop-back used to overshoot `len(node.deciders)`
            # and silently fall back to the gate's own permission instead of
            # this decider's.
            forbidden = _check_person_decider_permission(process, node_id, decider)
            if forbidden is not None:
                return _Advance(answer=forbidden)
            assert (
                decider.permission is not None
            )  # checked by _check_person_decider_permission
            permission_decision = await ctx.policy.authorize(
                decider.permission,
                identity=ctx.identity,
                platform_id=ctx.platform_id,
                run_id=run_id,
            )
            if permission_decision.verdict is not Verdict.PERMIT:
                return _Advance(
                    answer=_forbidden(
                        process,
                        permission_decision.rationale or "decision permission refused",
                    )
                )
            record = (
                _person_answer_record(
                    run_id,
                    scope,
                    node_id,
                    baseline + decider_index + 1,
                    pending_decision[1],
                )
                if node.kind == "INPUT"
                else _person_decision_record(
                    run_id,
                    scope,
                    node_id,
                    baseline + decider_index + 1,
                    pending_decision[1],
                )
            )
            await _record_attempt(ctx, record, run_id=run_id)
            return await _advance_gate(
                process,
                scope_def,
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
                kind=AnswerKind.AWAITING_DECISION,
                says=node.asks or "A decision is needed.",
                node_id=node_id,
                scope=scope,
            )
        )

    # PAUSED — every declared decider asked and answered INDETERMINATE, or
    # none were declared at all: D13's fallback, the gate's OWN permission
    # decides who may act, not any specific decider's.
    if pending_decision is not None and pending_decision[0] == "person":
        if node.permission is None:
            return _Advance(
                answer=_forbidden(
                    process,
                    f"gate {node_id!r} declares no permission for a person to "
                    "decide it here — refusing rather than accepting it unchecked.",
                )
            )
        permission_decision = await ctx.policy.authorize(
            node.permission,
            identity=ctx.identity,
            platform_id=ctx.platform_id,
            run_id=run_id,
        )
        if permission_decision.verdict is not Verdict.PERMIT:
            return _Advance(
                answer=_forbidden(
                    process,
                    permission_decision.rationale or "decision permission refused",
                )
            )
        record = (
            _person_answer_record(
                run_id,
                scope,
                node_id,
                baseline + len(attempts) + 1,
                pending_decision[1],
            )
            if node.kind == "INPUT"
            else _person_decision_record(
                run_id,
                scope,
                node_id,
                baseline + len(attempts) + 1,
                pending_decision[1],
            )
        )
        await _record_attempt(ctx, record, run_id=run_id)
        return await _advance_gate(
            process,
            scope_def,
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
            kind=AnswerKind.AWAITING_DECISION,
            says=node.asks or "A decision is needed.",
            node_id=node_id,
            scope=scope,
        )
    )


def _check_person_decider_permission(
    process: Process, node_id: str, decider: Decider
) -> NextAnswer | None:
    """A `person` decider declared with `role` instead of `permission` is
    refused outright — `PolicyPort.authorize()` has no way to check a
    role, only an opaque permission string, and nothing here invents one.
    Returns the refusal answer, or `None` when `decider.permission` is
    safe to use."""
    if decider.permission is None and decider.role is not None:
        return _forbidden(
            process,
            f"gate {node_id!r}: person decider declares `role`, which "
            "this engine's PolicyPort cannot check (permission strings "
            "only) — refusing rather than accepting an unchecked decision.",
        )
    if decider.permission is None:
        return _forbidden(
            process,
            f"gate {node_id!r} declares no permission for a person to "
            "decide it here — refusing rather than accepting it unchecked.",
        )
    return None


def _person_decision_record(
    run_id: str, scope: str, node_id: str, attempt: int, payload: Mapping[str, Any]
) -> AttemptRecord:
    verdict: Verdict = payload["verdict"]
    note: str | None = payload.get("note")
    subject: str = payload["subject"]
    return AttemptRecord(
        key=AttemptKey(run=run_id, scope=scope, node=node_id, attempt=attempt),
        inputs={},
        output={"note": note} if note else None,
        control_results=[],
        verdict=verdict.value,
        performed_by=f"PERSON:{subject}",
        started_at=_now(),
        ended_at=_now(),
    )


def _person_answer_record(
    run_id: str, scope: str, node_id: str, attempt: int, payload: Mapping[str, Any]
) -> AttemptRecord:
    """`kind: INPUT`'s own person-decider record (D26/D41) — parallel to
    `_person_decision_record`, but the payload's own shape has a `value`
    (already checked against `answer_type` in `decide()`, before this is
    ever called) where APPROVAL's has a `verdict`. There is deliberately
    no `on.INDETERMINATE`-equivalent "declines to answer" path for a
    person decider here — §7.6 only ever describes a person giving an
    answer, never withholding one; a gate simply stays `AWAITING_DECISION`
    until `decide(..., value=...)` is actually called.
    """
    subject: str = payload["subject"]
    value = payload["value"]
    return AttemptRecord(
        key=AttemptKey(run=run_id, scope=scope, node=node_id, attempt=attempt),
        inputs={},
        output={"value": value},
        control_results=[],
        verdict="ANSWERED",
        performed_by=f"PERSON:{subject}",
        started_at=_now(),
        ended_at=_now(),
    )


def _state_with_note(
    scope_def: _ScopeDef,
    node: GateNode,
    attempts: list[AttemptRecord],
    run_state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """This gate's decision note, written where the gate says it goes (§7.6).

    The latest note wins: a gate asked twice carries the decider's most recent
    words, not the first ones, or a second send-back would re-run the step with
    the previous round's instruction.

    D32: "the decider's reason" (D24's own problem statement) is not
    person-specific — a `policy` or `agent` decider's own `rationale` is
    the same kind of provenance content as a `person`'s own `note` (§7.6's
    Provenance bullet: "the rationale or note" are named side by side).
    Only a `person`'s record ever carries a `note` key; `policy`/`agent`
    records carry `rationale` instead — so this checks both, per attempt,
    preferring whichever this attempt actually has.

    D27: this recomputes and re-applies the SAME note on every call that
    replays through a DECIDED gate — safe only because `REPLACE` (last
    write wins) is idempotent under repeated application with the same
    value. `APPEND` is not: writing `[note]` on every replay would grow
    the target list once per replay pass rather than once per send-back, a
    silent corruption worse than the crash it would otherwise raise
    (`ReducerMismatch`, since a bare string isn't the list `APPEND`
    requires either). Both spec worked examples (§7.6, Appendix A) target
    an `APPEND` channel with `note_into`, so this refuses rather than
    guessing at APPEND's own "once per send-back" semantics, which §7.6
    does not state — V9 refuses the same gap at validation time; this is
    the runtime half, in case validation is bypassed.
    """
    if not node.note_into:
        return None
    note = next(
        (
            (record.output or {}).get("note") or (record.output or {}).get("rationale")
            for record in reversed(attempts)
            if (record.output or {}).get("note")
            or (record.output or {}).get("rationale")
        ),
        None,
    )
    if not note:
        return None
    channel_name = (
        node.note_into[len("state.") :] if node.note_into.startswith("state.") else None
    )
    channel = scope_def.state.get(channel_name) if channel_name is not None else None
    reducer = channel.reducer if channel is not None else "REPLACE"
    if reducer != "REPLACE":
        raise EngineRefusal(
            f"gate {node.id!r}: note_into targets {node.note_into!r}, a "
            f"{reducer} channel — only a REPLACE channel is supported (D27); "
            "APPEND/MERGE/UPSERT_BY_ID would accumulate the same note again "
            "on every replay rather than writing it once per send-back"
        )
    return apply_output(
        scope_def.state, run_state["state"], {"note": node.note_into}, {"note": note}
    )


def _state_with_answer(
    scope_def: _ScopeDef,
    node: GateNode,
    value: Any,
    base_state: Mapping[str, Any],
) -> dict[str, Any]:
    """`kind: INPUT`'s own `answer_into` (§7.6, D26/D41) — the decider's
    answer, written to state at the point of decision. Mirrors
    `_state_with_note`'s own REPLACE-only restriction and D27's reasoning
    exactly: this recomputes and reapplies the SAME value on every replay
    pass that reaches this already-DECIDED gate, safe only for a REPLACE
    channel (APPEND/MERGE/UPSERT_BY_ID would accumulate or re-key it
    again on every replay rather than writing it once)."""
    assert node.answer_into is not None  # V9 requires it for kind: INPUT
    channel_name = (
        node.answer_into[len("state.") :]
        if node.answer_into.startswith("state.")
        else None
    )
    channel = scope_def.state.get(channel_name) if channel_name is not None else None
    reducer = channel.reducer if channel is not None else "REPLACE"
    if reducer != "REPLACE":
        raise EngineRefusal(
            f"gate {node.id!r}: answer_into targets {node.answer_into!r}, a "
            f"{reducer} channel — only a REPLACE channel is supported, "
            "mirroring note_into's own restriction (D27) for the same reason"
        )
    return apply_output(
        scope_def.state, base_state, {"value": node.answer_into}, {"value": value}
    )


def _outcome_from_record(index: int, record: AttemptRecord) -> DeciderOutcome:
    return DeciderOutcome(
        decider_index=index,
        verdict=Verdict(record.verdict),
        decided_by=record.performed_by,
        evidence=tuple((record.output or {}).get("evidence", ())),
    )


def _answer_from_record(index: int, record: AttemptRecord) -> AnswerOutcome:
    """`kind: INPUT`'s own counterpart to `_outcome_from_record` (D26/D41)
    — replays one durable attempt back into an `AnswerOutcome`. `answered`
    is keyed off `record.verdict == "ANSWERED"` (the only value this
    engine ever writes there for an INPUT gate's attempt — see
    `_person_answer_record`, and the `NEEDS_POLICY`/`NEEDS_AGENT` branches
    of `_advance_gate`, which always write `"INDETERMINATE"` instead)."""
    answered = record.verdict == "ANSWERED"
    output = record.output or {}
    return AnswerOutcome(
        decider_index=index,
        answered=answered,
        decided_by=record.performed_by,
        value=output.get("value") if answered else None,
        rationale=output.get("rationale"),
    )


def _evaluate(expr: str, run_state: Mapping[str, Any]) -> Any:
    return evaluate(parse(expr), run_state)
