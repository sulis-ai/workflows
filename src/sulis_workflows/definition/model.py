"""Typed model for the v1 process-definition format (spec §§1-11).

Frozen dataclasses, built from a document already validated against its JSON Schema
(``schema.py`` / ``load.py``) — every field here mirrors a shape the schema already
closed, so construction does not re-validate types or unknown keys. What this module
*does* resolve is the handful of node-level defaults the spec states inline rather
than through the overridable §15 table (e.g. "kind: APPROVAL | INPUT; absent means
APPROVAL") — see ``defaults.py`` for the boundary between the two.

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sulis_workflows.definition import defaults as fmt_defaults

MISSING = object()
"""Sentinel: distinguishes 'no default declared' from 'default is null'."""


# --------------------------------------------------------------------------- header --


@dataclass(frozen=True, slots=True)
class Header:
    api_version: str
    kind: str
    id: str
    version: str
    title: str
    summary: str | None = None


# ------------------------------------------------------------------------ shared bits --


@dataclass(frozen=True, slots=True)
class InputSpec:
    type: str
    required: bool = True
    default: Any = MISSING
    description: str | None = None

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING


@dataclass(frozen=True, slots=True)
class OutputSpec:
    type: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: str
    error_class: str  # TRANSIENT | PERMANENT


@dataclass(frozen=True, slots=True)
class ComposeItem:
    tool: str
    inputs: Mapping[str, str | list[str]] = field(default_factory=dict)
    output: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CallResult:
    outputs: Mapping[str, str] = field(default_factory=dict)
    endings: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Mechanism:
    kind: str  # CODE | SKILL | AGENTIC | PROCESS | TOOL | EXTERNAL
    ref: str | None = None
    allowed_tools: tuple[str, ...] = ()
    composes: tuple[ComposeItem, ...] = ()
    inputs: Mapping[str, str | list[str]] = field(default_factory=dict)
    path: str | None = None
    result: CallResult | None = None


@dataclass(frozen=True, slots=True)
class ControlRef:
    kind: str  # profile | conventions | fitness | policy
    ref: str


@dataclass(frozen=True, slots=True)
class Example:
    name: str
    inputs: Mapping[str, Any]
    expect: Mapping[str, Any]


# --------------------------------------------------------------------------- Profile --


@dataclass(frozen=True, slots=True)
class Profile:
    header: Header
    schema: Mapping[str, Any]
    grounded_in: str | None = None
    checker: str | None = None


# ------------------------------------------------------------------------------ Tool --


@dataclass(frozen=True, slots=True)
class Tool:
    header: Header
    output: Mapping[str, OutputSpec]
    controls: tuple[ControlRef, ...]
    mechanism: Mechanism
    effect: str  # QUERY | MUTATION | SIDE_EFFECT
    inputs: Mapping[str, InputSpec] = field(default_factory=dict)
    errors: tuple[ErrorSpec, ...] = ()
    checker_for: str | None = None
    examples: tuple[Example, ...] = ()
    permission: str | None = None  # host's opaque grammar (ADR-024); spec §10.1, D12


# --------------------------------------------------------------------------- Control --


@dataclass(frozen=True, slots=True)
class ThresholdSpec:
    metric: str
    op: str  # GTE | GT | LTE | LT | EQ
    value: float


@dataclass(frozen=True, slots=True)
class Control:
    header: Header
    type: str  # CONVENTIONS | FITNESS | POLICY
    applies_to: str | None = None
    checker: str | None = None
    grounded_in: str | None = None
    severity: str | None = None  # ERROR | WARNING (FITNESS only)
    threshold: ThresholdSpec | None = None  # FITNESS only (spec §5.1, D8)


# ----------------------------------------------------------------------- Process bits --


@dataclass(frozen=True, slots=True)
class RouteTarget:
    next: str | None = None
    end: str | None = None
    call: str | None = None
    loop: LoopSpec | None = None
    invalidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LoopSpec:
    budget: int | None = None
    on_exhausted: RouteTarget | None = None
    counts: str | None = None  # PASSES | FAILURES


@dataclass(frozen=True, slots=True)
class RetrySpec:
    max: int | None = None
    backoff_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ControlFail:
    repair: int | None = None
    then: RouteTarget | None = None


@dataclass(frozen=True, slots=True)
class StepNode:
    id: str
    tool: str
    in_: Mapping[str, str | list[str]]
    out: Mapping[str, str]
    precondition: str | None = None
    criticality: str | None = None
    destructive: bool = False
    retry: RetrySpec | None = None
    on_control_fail: ControlFail | None = None
    on_error: Mapping[str, RouteTarget] = field(default_factory=dict)
    on_forbidden: RouteTarget | None = None
    on_precondition_false: RouteTarget | None = None
    on_depth_exhausted: RouteTarget | None = None
    next: str | None = None
    end: str | None = None
    type: str = "STEP"


@dataclass(frozen=True, slots=True)
class RouteOption:
    if_: str
    next: str | None = None
    end: str | None = None
    call: str | None = None
    loop: LoopSpec | None = None
    invalidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RouteNode:
    id: str
    when: tuple[RouteOption, ...]
    otherwise: RouteTarget | None = None
    type: str = "ROUTE"


@dataclass(frozen=True, slots=True)
class ParallelNode:
    id: str
    branches: tuple[str, ...]
    join: str
    type: str = "PARALLEL"


@dataclass(frozen=True, slots=True)
class JoinNode:
    id: str
    policy: str | None = None  # ALL_SUCCESS | ANY_SUCCESS | ALL_COMPLETE
    on_join_failed: RouteTarget | None = None
    next: str | None = None
    end: str | None = None
    type: str = "JOIN"


@dataclass(frozen=True, slots=True)
class CollectSpec:
    output: str
    into: str


@dataclass(frozen=True, slots=True)
class ForEachNode:
    id: str
    over: str
    as_: str
    do: str
    max_concurrency: int | None = None
    collect: CollectSpec | None = None
    join: str | None = None
    next: str | None = None
    end: str | None = None
    type: str = "FOR_EACH"


@dataclass(frozen=True, slots=True)
class Decider:
    kind: str  # policy | agent | person
    ref: str | None = None  # policy@v / agent@v
    permission: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class GateNode:
    id: str
    kind: str  # APPROVAL | INPUT — resolved: absent means APPROVAL (spec §7.6)
    asks: str | None = None
    criteria: str | None = None
    reviewing: tuple[str, ...] = ()
    deciders: tuple[Decider, ...] = ()
    person_required_when: str | None = None
    note_into: str | None = None
    answer_type: str | None = None
    answer_into: str | None = None
    on: Mapping[str, RouteTarget] = field(default_factory=dict)
    permission: str | None = None  # host's opaque grammar (ADR-024); spec §7.6, D13
    type: str = "GATE"


Node = StepNode | RouteNode | ParallelNode | JoinNode | ForEachNode | GateNode


@dataclass(frozen=True, slots=True)
class StateChannel:
    type: str
    reducer: str  # REPLACE | MERGE | APPEND | UPSERT_BY_ID
    key: str | None = None
    default: Any = MISSING

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING


@dataclass(frozen=True, slots=True)
class Ending:
    outcome: str  # SUCCESS | STOPPED | FAILURE
    says: str


@dataclass(frozen=True, slots=True)
class Trigger:
    kind: str  # TIMER | EVENT | STATE_ENTRY | WEBHOOK | BRANCH_PUSH
    rrule: str | None = None
    event: str | None = None
    inputs: Mapping[str, Any] = field(default_factory=dict)
    process: str | None = None
    ending: str | None = None
    adapter: str | None = None
    repository: str | None = None
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class ProcessDefaults:
    loop_budget: int | None = None
    repair_budget: int | None = None
    retry: RetrySpec | None = None
    max_depth: int | None = None


@dataclass(frozen=True, slots=True)
class Process:
    header: Header
    start: str
    nodes: Mapping[str, Node]
    endings: Mapping[str, Ending]
    inputs: Mapping[str, InputSpec] = field(default_factory=dict)
    host_inputs: Mapping[str, InputSpec] = field(default_factory=dict)
    state: Mapping[str, StateChannel] = field(default_factory=dict)
    defaults: ProcessDefaults | None = None
    triggers: tuple[Trigger, ...] = ()
    execution_policy: str = fmt_defaults.EXECUTION_POLICY


Definition = Profile | Tool | Control | Process


# ------------------------------------------------------------------------- builders --


def _input_spec(d: Mapping[str, Any]) -> InputSpec:
    return InputSpec(
        type=d["type"],
        required=d.get("required", True),
        default=d.get("default", MISSING),
        description=d.get("description"),
    )


def _output_spec(d: Mapping[str, Any]) -> OutputSpec:
    return OutputSpec(type=d["type"], description=d.get("description"))


def _route_target(d: Mapping[str, Any] | None) -> RouteTarget | None:
    if d is None:
        return None
    return _route_target_required(d)


def _route_target_required(d: Mapping[str, Any]) -> RouteTarget:
    """Same shape as :func:`_route_target`, for call sites (a dict's *values*,
    e.g. `on_error`/`on`) where the mapping is never itself absent — only used
    to give mypy a non-Optional return type there."""

    return RouteTarget(
        next=d.get("next"),
        end=d.get("end"),
        call=d.get("call"),
        loop=_loop_spec(d.get("loop")),
        invalidates=tuple(d.get("invalidates", ())),
    )


def _loop_spec(d: Mapping[str, Any] | None) -> LoopSpec | None:
    if d is None:
        return None
    return LoopSpec(
        budget=d.get("budget"),
        on_exhausted=_route_target(d.get("on_exhausted")),
        counts=d.get("counts"),
    )


def _retry_spec(d: Mapping[str, Any] | None) -> RetrySpec | None:
    if d is None:
        return None
    return RetrySpec(max=d.get("max"), backoff_seconds=d.get("backoff_seconds"))


def _control_fail(d: Mapping[str, Any] | None) -> ControlFail | None:
    if d is None:
        return None
    return ControlFail(repair=d.get("repair"), then=_route_target(d.get("then")))


def _control_ref(d: Mapping[str, Any]) -> ControlRef:
    for kind in ("profile", "conventions", "fitness", "policy"):
        if kind in d:
            return ControlRef(kind=kind, ref=d[kind])
    raise ValueError(
        f"control reference has none of profile/conventions/fitness/policy: {d!r}"
    )


def _mechanism(d: Mapping[str, Any]) -> Mechanism:
    return Mechanism(
        kind=d["kind"],
        ref=d.get("ref"),
        allowed_tools=tuple(d.get("allowed_tools", ())),
        composes=tuple(
            ComposeItem(
                tool=c["tool"], inputs=c.get("inputs", {}), output=c.get("output", {})
            )
            for c in d.get("composes", ())
        ),
        inputs=d.get("inputs", {}),
        path=d.get("path"),
        result=(
            CallResult(
                outputs=d["result"].get("outputs", {}),
                endings=d["result"].get("endings", {}),
            )
            if d.get("result") is not None
            else None
        ),
    )


def _decider(d: Mapping[str, Any]) -> Decider:
    if "policy" in d:
        return Decider(kind="policy", ref=d["policy"])
    if "agent" in d:
        return Decider(kind="agent", ref=d["agent"])
    person = d["person"]
    return Decider(
        kind="person", permission=person.get("permission"), role=person.get("role")
    )


def _node(node_id: str, d: Mapping[str, Any]) -> Node:
    node_type = d["type"]
    if node_type == "STEP":
        return StepNode(
            id=node_id,
            tool=d["tool"],
            in_=d.get("in", {}),
            out=d.get("out", {}),
            precondition=d.get("precondition"),
            criticality=d.get("criticality"),
            destructive=d.get("destructive", False),
            retry=_retry_spec(d.get("retry")),
            on_control_fail=_control_fail(d.get("on_control_fail")),
            on_error={
                k: _route_target_required(v) for k, v in d.get("on_error", {}).items()
            },
            on_forbidden=_route_target(d.get("on_forbidden")),
            on_precondition_false=_route_target(d.get("on_precondition_false")),
            on_depth_exhausted=_route_target(d.get("on_depth_exhausted")),
            next=d.get("next"),
            end=d.get("end"),
        )
    if node_type == "ROUTE":
        return RouteNode(
            id=node_id,
            when=tuple(
                RouteOption(
                    if_=opt["if"],
                    next=opt.get("next"),
                    end=opt.get("end"),
                    call=opt.get("call"),
                    loop=_loop_spec(opt.get("loop")),
                    invalidates=tuple(opt.get("invalidates", ())),
                )
                for opt in d["when"]
            ),
            otherwise=_route_target(d.get("otherwise")),
        )
    if node_type == "PARALLEL":
        return ParallelNode(id=node_id, branches=tuple(d["branches"]), join=d["join"])
    if node_type == "JOIN":
        return JoinNode(
            id=node_id,
            policy=d.get("policy"),
            on_join_failed=_route_target(d.get("on_join_failed")),
            next=d.get("next"),
            end=d.get("end"),
        )
    if node_type == "FOR_EACH":
        collect = d.get("collect")
        return ForEachNode(
            id=node_id,
            over=d["over"],
            as_=d["as"],
            do=d["do"],
            max_concurrency=d.get("max_concurrency"),
            collect=CollectSpec(output=collect["output"], into=collect["into"])
            if collect
            else None,
            join=d.get("join"),
            next=d.get("next"),
            end=d.get("end"),
        )
    if node_type == "GATE":
        return GateNode(
            id=node_id,
            kind=d.get("kind", fmt_defaults.GATE_KIND),
            asks=d.get("asks"),
            criteria=d.get("criteria"),
            reviewing=tuple(d.get("reviewing", ())),
            deciders=tuple(_decider(x) for x in d.get("deciders", ())),
            person_required_when=d.get("person_required_when"),
            note_into=d.get("note_into"),
            answer_type=d.get("answer_type"),
            answer_into=d.get("answer_into"),
            on={k: _route_target_required(v) for k, v in d.get("on", {}).items()},
            permission=d.get("permission"),
        )
    raise ValueError(f"unknown node type {node_type!r} for node {node_id!r}")


def _state_channel(d: Mapping[str, Any]) -> StateChannel:
    return StateChannel(
        type=d["type"],
        reducer=d["reducer"],
        key=d.get("key"),
        default=d.get("default", MISSING),
    )


def _trigger(d: Mapping[str, Any]) -> Trigger:
    return Trigger(
        kind=d["kind"],
        rrule=d.get("rrule"),
        event=d.get("event"),
        inputs=d.get("inputs", {}),
        process=d.get("process"),
        ending=d.get("ending"),
        adapter=d.get("adapter"),
        repository=d.get("repository"),
        branch=d.get("branch"),
    )


def _process_defaults(d: Mapping[str, Any] | None) -> ProcessDefaults | None:
    if d is None:
        return None
    return ProcessDefaults(
        loop_budget=d.get("loop_budget"),
        repair_budget=d.get("repair_budget"),
        retry=_retry_spec(d.get("retry")),
        max_depth=d.get("max_depth"),
    )


def _header(d: Mapping[str, Any]) -> Header:
    return Header(
        api_version=d["api_version"],
        kind=d["kind"],
        id=d["id"],
        version=d["version"],
        title=d["title"],
        summary=d.get("summary"),
    )


def build(doc: Mapping[str, Any]) -> Definition:
    """Build a typed model object from a document already validated against its schema.

    Dispatches on ``kind``; raises :class:`KeyError`/:class:`ValueError` only for shapes
    the JSON Schema should already have refused — those are programming errors in the
    caller (an unvalidated document), not a document-authoring mistake to report nicely.
    """

    header = _header(doc)
    kind = header.kind
    if kind == "PROFILE":
        return Profile(
            header=header,
            schema=doc["schema"],
            grounded_in=doc.get("grounded_in"),
            checker=doc.get("checker"),
        )
    if kind == "CONTROL":
        threshold = doc.get("threshold")
        return Control(
            header=header,
            type=doc["type"],
            applies_to=doc.get("applies_to"),
            checker=doc.get("checker"),
            grounded_in=doc.get("grounded_in"),
            severity=doc.get("severity"),
            threshold=(
                ThresholdSpec(
                    metric=threshold["metric"],
                    op=threshold["op"],
                    value=threshold["value"],
                )
                if threshold is not None
                else None
            ),
        )
    if kind == "TOOL":
        return Tool(
            header=header,
            inputs={k: _input_spec(v) for k, v in doc.get("inputs", {}).items()},
            output={k: _output_spec(v) for k, v in doc["output"].items()},
            controls=tuple(_control_ref(c) for c in doc["controls"]),
            mechanism=_mechanism(doc["mechanism"]),
            effect=doc["effect"],
            errors=tuple(
                ErrorSpec(code=e["code"], error_class=e["class"])
                for e in doc.get("errors", ())
            ),
            checker_for=(
                doc["checker_for"]["control"] if doc.get("checker_for") else None
            ),
            examples=tuple(
                Example(name=e["name"], inputs=e["inputs"], expect=e["expect"])
                for e in doc.get("examples", ())
            ),
            permission=doc.get("permission"),
        )
    if kind == "PROCESS":
        return Process(
            header=header,
            inputs={k: _input_spec(v) for k, v in doc.get("inputs", {}).items()},
            host_inputs={
                k: _input_spec(v) for k, v in doc.get("host_inputs", {}).items()
            },
            state={k: _state_channel(v) for k, v in doc.get("state", {}).items()},
            defaults=_process_defaults(doc.get("defaults")),
            start=doc["start"],
            nodes={node_id: _node(node_id, n) for node_id, n in doc["nodes"].items()},
            endings={
                k: Ending(outcome=v["outcome"], says=v["says"])
                for k, v in doc["endings"].items()
            },
            triggers=tuple(_trigger(t) for t in doc.get("triggers", ())),
            execution_policy=doc.get("execution_policy", fmt_defaults.EXECUTION_POLICY),
        )
    raise ValueError(f"unknown kind {kind!r}")
