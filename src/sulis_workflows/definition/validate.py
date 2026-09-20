"""The v1 format's validator — spec §14, rules V1-V16. Each rule is a separate,
named function returning structured :class:`Finding`s (`{ rule, node, message,
fix }`). V1 (schema) and V2 (references) are already enforced by `load.py` and
`registry.py`; :func:`validate` wraps their refusals into the same Finding shape
so a caller (the CLI, WP-01 step 4) gets every problem from one call, in one
report, rather than stopping at the first.

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from sulis_workflows.definition import model
from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.expressions import (
    Compare,
    Literal,
    Path,
    TEnum,
    TList,
    Type,
    TypeContext,
    infer_type,
    parse,
)
from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry

__all__ = [
    "Finding",
    "validate",
    "validate_control",
    "validate_definition",
    "validate_process",
    "validate_profile",
    "validate_tool",
]

_ENGINE_ENDINGS = ("ESCALATED", "FAILED", "FORBIDDEN", "CANCELLED")


@dataclass(frozen=True, slots=True)
class Finding:
    rule: str
    message: str
    node: str | None = None
    fix: str | None = None


# ------------------------------------------------------------------------- entry --


def validate(
    text: str, *, fmt: str = "yaml", registry: Registry | None = None
) -> list[Finding]:
    """Parse, then run every rule this document's kind is subject to. `registry`
    supplies every other definition this document references (V2), and — for
    V10's depth-exhaustion check — every other Process, so a self-reachable call
    can be detected across documents, not only within this one."""

    registry = registry if registry is not None else Registry()
    try:
        definition = load_definition(text, fmt=fmt)
    except DefinitionError as exc:
        return [
            Finding(
                rule=exc.rule, message=exc.message, node=exc.node, fix=exc.schema_path
            )
        ]
    return validate_definition(definition, registry)


def validate_definition(
    definition: model.Definition, registry: Registry
) -> list[Finding]:
    """Validate an already-loaded definition (skipping the parse step `validate`
    does) — for a caller, such as the CLI, that loads several files into one
    registry before validating any of them, so cross-file references resolve."""

    if isinstance(definition, model.Profile):
        return validate_profile(definition, registry)
    if isinstance(definition, model.Control):
        return validate_control(definition, registry)
    if isinstance(definition, model.Tool):
        return validate_tool(definition, registry)
    if isinstance(definition, model.Process):
        return validate_process(definition, registry)
    raise AssertionError(
        f"unreachable: unknown definition type {type(definition)!r}"
    )  # pragma: no cover


_PROFILE_REF_RE = re.compile(r"profile:([a-z][a-z0-9-]*@\^?\d+(?:\.\d+){0,2})")


def _v2_profile_type_refs(
    type_strings: Any, registry: Registry, *, node: str | None = None
) -> list[Finding]:
    """A `profile:<id>@<version>` embedded in a declared type — bare, or nested
    inside `list<...>`/`map<...>` — is a reference too (spec §2.1); walking
    type strings for it is what makes removing a corpus Profile actually break
    validation (WP-01 A2), not just its own Tool/Process document's `controls`."""

    findings: list[Finding] = []
    for type_string in type_strings:
        for ref in _PROFILE_REF_RE.findall(type_string):
            _, err = _resolve(registry, "PROFILE", ref)
            if err:
                findings.append(Finding(rule="V2", node=node, message=err.message))
    return findings


def _resolve(
    registry: Registry, kind: str, ref: str | None
) -> tuple[Any, Finding | None]:
    if ref is None:
        return None, None
    try:
        return registry.resolve(kind, ref), None
    except DefinitionError as exc:
        return None, Finding(rule="V2", message=exc.message)


# ------------------------------------------------------------------------ profile --


def validate_profile(profile: model.Profile, registry: Registry) -> list[Finding]:
    findings = list(v15_grounding_profile(profile))
    if profile.checker:
        _, err = _resolve(registry, "TOOL", profile.checker)
        if err:
            findings.append(err)
    return findings


def v15_grounding_profile(profile: model.Profile) -> list[Finding]:
    """A closed value set (a JSON Schema `enum` anywhere in the Profile's own
    embedded schema) with no `grounded_in` on the Profile that declares it."""

    if (
        _schema_declares_an_enum(profile.schema)
        and not (profile.grounded_in or "").strip()
    ):
        return [
            Finding(
                rule="V15",
                message=(
                    f"profile {profile.header.id!r} declares a closed value set (an `enum` in its "
                    "schema) but has no `grounded_in`"
                ),
                fix="add grounded_in: naming the standard this value set comes from, or state plainly "
                "that it is this format's own convention",
            )
        ]
    return []


def _schema_declares_an_enum(node: Any) -> bool:
    if isinstance(node, dict):
        if "enum" in node:
            return True
        return any(_schema_declares_an_enum(v) for v in node.values())
    if isinstance(node, list):
        return any(_schema_declares_an_enum(v) for v in node)
    return False


# ------------------------------------------------------------------------- control --


def validate_control(control: model.Control, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(v3_control_checker(control))
    if control.checker:
        _, err = _resolve(registry, "TOOL", control.checker)
        if err:
            findings.append(err)
    return findings


def v3_control_checker(control: model.Control) -> list[Finding]:
    """A non-policy control with no checker (spec §4.4, §5.1)."""

    if control.type != "POLICY" and not (control.checker or "").strip():
        return [
            Finding(
                rule="V3",
                message=f"control {control.header.id!r} is type {control.type} but has no checker",
                fix="add checker: <id@version> of a registered checker Tool",
            )
        ]
    return []


# ---------------------------------------------------------------------------- tool --


def validate_tool(tool: model.Tool, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(v3_tool_controls(tool, registry))
    findings.extend(v3_checker_examples(tool))
    for control_ref in tool.controls:
        if control_ref.kind in ("conventions", "fitness", "policy"):
            _, err = _resolve(registry, "CONTROL", control_ref.ref)
            if err:
                findings.append(err)
        elif control_ref.kind == "profile":
            _, err = _resolve(registry, "PROFILE", control_ref.ref)
            if err:
                findings.append(err)
    findings.extend(_v2_mechanism_references(tool.mechanism, registry))
    type_strings = [i.type for i in tool.inputs.values()] + [
        o.type for o in tool.output.values()
    ]
    findings.extend(_v2_profile_type_refs(type_strings, registry))
    return findings


def _v2_mechanism_references(
    mechanism: model.Mechanism, registry: Registry
) -> list[Finding]:
    """`ref`/`composes`/`allowed_tools` are `id@version` references where the
    mechanism kind makes them one (spec §4.3); CODE/SKILL's own `ref`
    names a module or skill path, not a registered definition, so only a
    referenced (not inline, D18) PROCESS's `ref`, TOOL(composite)'s
    `composes[].tool`, and SKILL's `allowed_tools[]` are checked here.
    An inline PROCESS's own internal `tool:` references are not yet
    resolved by this function (untouched — no fixture exercises one)."""

    findings: list[Finding] = []
    if mechanism.kind == "PROCESS" and mechanism.ref:
        _, err = _resolve(registry, "PROCESS", mechanism.ref)
        if err:
            findings.append(err)
    elif mechanism.kind == "TOOL":
        for item in mechanism.composes:
            _, err = _resolve(registry, "TOOL", item.tool)
            if err:
                findings.append(err)
    if mechanism.kind == "SKILL":
        for ref in mechanism.allowed_tools:
            _, err = _resolve(registry, "TOOL", ref)
            if err:
                findings.append(err)
    return findings


def v3_tool_controls(tool: model.Tool, registry: Registry) -> list[Finding]:
    """A Tool with no control; a SKILL Tool with only policy controls."""

    findings: list[Finding] = []
    if not tool.controls:
        findings.append(
            Finding(
                rule="V3",
                message=f"tool {tool.header.id!r} declares no controls",
                fix="add at least one control (profile/conventions/fitness/policy)",
            )
        )
    if tool.mechanism.kind == "SKILL":
        has_non_policy = any(c.kind != "policy" for c in tool.controls)
        if tool.controls and not has_non_policy:
            findings.append(
                Finding(
                    rule="V3",
                    message=(
                        f"tool {tool.header.id!r} is {tool.mechanism.kind} but its only control is a "
                        "policy — its output varies and has no checkable bar"
                    ),
                    fix="add a profile, conventions or fitness control",
                )
            )
    return findings


def _is_checker(tool: model.Tool) -> bool:
    """spec §5.2 defines a checker by what it returns ("A checker is a `CODE`
    Tool that... returns `profile:control-result@1`"), not by declaring
    `checker_for` — that field only marks the *generic* checker for a control
    kind (e.g. `profile-conformance@1` for every `profile:` control). A
    specific checker wired through a Profile's own `checker:` field (e.g.
    `decision-evidence@1`) is still a checker and still owes the spec's pass
    + fail example requirement."""

    return any(o.type == "profile:control-result@1" for o in tool.output.values())


def v3_checker_examples(tool: model.Tool) -> list[Finding]:
    """A checker with only passing examples, or only failing ones — it must
    ship both (spec §5.2)."""

    if not _is_checker(tool):
        return []
    saw_pass = False
    saw_fail = False
    for example in tool.examples:
        result = (
            example.expect.get("result") if isinstance(example.expect, dict) else None
        )
        passed = result.get("passed") if isinstance(result, dict) else None
        if passed is True:
            saw_pass = True
        elif passed is False:
            saw_fail = True
    if not (saw_pass and saw_fail):
        return [
            Finding(
                rule="V3",
                message=(
                    f"checker {tool.header.id!r} must ship at least one passing and one failing example "
                    f"(has passing={saw_pass}, failing={saw_fail})"
                ),
                fix="add an examples[] entry with expect.result.passed: true and one with false",
            )
        ]
    return []


# ------------------------------------------------------------------------ process --


def validate_process(process: model.Process, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    ctx = TypeContext(process, registry)

    findings.extend(_v2_process_references(process, registry))
    process_type_strings = (
        [i.type for i in process.inputs.values()]
        + [i.type for i in process.host_inputs.values()]
        + [s.type for s in process.state.values()]
    )
    findings.extend(_v2_profile_type_refs(process_type_strings, registry))
    findings.extend(v4_mappings(process, registry, ctx))
    findings.extend(v5_expressions(process, ctx))
    findings.extend(v6_routes(process, ctx))
    findings.extend(v7_reachability(process))
    findings.extend(v8_loops(process))
    findings.extend(v9_gates(process, registry))
    findings.extend(v10_calls(process, registry))
    findings.extend(v11_parallel(process))
    findings.extend(v12_for_each(process, ctx))
    findings.extend(v13_side_effects(process))
    findings.extend(v14_endings(process))
    findings.extend(v16_state_channels(process))
    return findings


def _v2_process_references(process: model.Process, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if isinstance(node, model.StepNode):
            _, err = _resolve(registry, "TOOL", node.tool)
            if err:
                findings.append(Finding(rule="V2", node=node_id, message=err.message))
        elif isinstance(node, model.GateNode):
            for decider in node.deciders:
                if decider.kind == "policy":
                    _, err = _resolve(registry, "CONTROL", decider.ref)
                elif decider.kind == "agent":
                    _, err = _resolve(registry, "TOOL", decider.ref)
                else:
                    err = None
                if err:
                    findings.append(
                        Finding(rule="V2", node=node_id, message=err.message)
                    )
    for trigger in process.triggers:
        if trigger.kind == "STATE_ENTRY" and trigger.process:
            _, err = _resolve(registry, "PROCESS", trigger.process)
            if err:
                findings.append(Finding(rule="V2", message=err.message))
    return findings


# ------------------------------------------------------------------------ V4 --


def v4_mappings(
    process: model.Process, registry: Registry, ctx: TypeContext
) -> list[Finding]:
    """An unmapped required input; a type mismatch in `in`, `out` or `collect`."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if isinstance(node, model.StepNode):
            findings.extend(_v4_step(node_id, node, registry, ctx))
        elif isinstance(node, model.ForEachNode):
            findings.extend(_v4_for_each(node_id, node, process, registry, ctx))
    return findings


def _v4_step(
    node_id: str, node: model.StepNode, registry: Registry, ctx: TypeContext
) -> Iterator[Finding]:
    tool, err = _resolve(registry, "TOOL", node.tool)
    if err or tool is None:
        return
    for name, input_spec in tool.inputs.items():
        if input_spec.required and not input_spec.has_default and name not in node.in_:
            yield Finding(
                rule="V4",
                node=node_id,
                message=f"step {node_id!r} does not map required input {name!r} of tool {node.tool!r}",
                fix=f"add `in: {{ {name}: <path> }}`",
            )
    for input_name, path_or_paths in node.in_.items():
        if input_name not in tool.inputs:
            continue
        declared = _parse_type_or_none(tool.inputs[input_name].type)
        paths: list[str] = (
            list(path_or_paths)
            if isinstance(path_or_paths, (list, tuple))
            else [path_or_paths]
        )
        for path_text in paths:
            actual = _resolve_path_type(path_text, ctx)
            if (
                declared is not None
                and actual is not None
                and not _types_compatible(declared, actual)
            ):
                yield Finding(
                    rule="V4",
                    node=node_id,
                    message=(
                        f"step {node_id!r}: input {input_name!r} expects {tool.inputs[input_name].type!r}, "
                        f"but {path_text!r} is {_type_repr(actual)!r}"
                    ),
                )
    for output_name, dest_path in node.out.items():
        if output_name not in tool.output:
            continue
        declared = _parse_type_or_none(tool.output[output_name].type)
        actual = _resolve_path_type(dest_path, ctx)
        if (
            declared is not None
            and actual is not None
            and not _types_compatible(actual, declared)
        ):
            yield Finding(
                rule="V4",
                node=node_id,
                message=(
                    f"step {node_id!r}: output {output_name!r} is {tool.output[output_name].type!r}, "
                    f"but {dest_path!r} expects {_type_repr(actual)!r}"
                ),
            )


def _v4_for_each(
    node_id: str,
    node: model.ForEachNode,
    process: model.Process,
    registry: Registry,
    ctx: TypeContext,
) -> Iterator[Finding]:
    if node.collect is None:
        return
    do_node = process.nodes.get(node.do)
    if not isinstance(do_node, model.StepNode):
        return
    tool, err = _resolve(registry, "TOOL", do_node.tool)
    if err or tool is None or node.collect.output not in tool.output:
        return
    item_type = _parse_type_or_none(tool.output[node.collect.output].type)
    into_type = _resolve_path_type(node.collect.into, ctx)
    if item_type is None or into_type is None:
        return
    if not isinstance(into_type, TList) or not _types_compatible(
        into_type.item, item_type
    ):
        yield Finding(
            rule="V4",
            node=node_id,
            message=(
                f"for_each {node_id!r}: collect.into {node.collect.into!r} does not accept a list of "
                f"{_type_repr(item_type)!r}"
            ),
        )


def _parse_type_or_none(type_string: str) -> Type | None:
    try:
        from sulis_workflows.definition.expressions import parse_type

        return parse_type(type_string)
    except DefinitionError:
        return None


def _as_bare_path(expr: Any) -> Path | None:
    """`parse()` wraps every bare value in `Compare(op=None)` (grammar: `cmp :=
    value (op value)?`) — unwrap that to get the `Path` a mapping field (`in`,
    `out`, `over`, `collect.into`) actually is."""

    if isinstance(expr, Compare) and expr.op is None and isinstance(expr.left, Path):
        return expr.left
    return expr if isinstance(expr, Path) else None


def _resolve_path_type(path_text: str, ctx: TypeContext) -> Type | None:
    try:
        expr = parse(path_text)
    except DefinitionError:
        return None
    path = _as_bare_path(expr)
    if path is None:
        return None
    try:
        return ctx.resolve(path)
    except DefinitionError:
        return None


def _type_repr(t: Type) -> str:
    if isinstance(t, TEnum):
        return f"enum[{', '.join(t.members)}]"
    if isinstance(t, TList):
        return f"list<{_type_repr(t.item)}>"
    return type(t).__name__


def _types_compatible(declared: Type, actual: Type) -> bool:
    from sulis_workflows.definition.expressions import (
        TAny,
        TInteger,
        TMap,
        TNumber,
        TProfile,
    )

    if isinstance(declared, TAny) or isinstance(actual, TAny):
        return True
    if isinstance(declared, TEnum) and isinstance(actual, TEnum):
        return set(actual.members) <= set(declared.members)
    if isinstance(declared, TList) and isinstance(actual, TList):
        return _types_compatible(declared.item, actual.item)
    if isinstance(declared, TMap) and isinstance(actual, TMap):
        return _types_compatible(declared.item, actual.item)
    if isinstance(declared, TProfile) and isinstance(actual, TProfile):
        return declared.ref.split("@")[0] == actual.ref.split("@")[0]
    if isinstance(declared, TNumber) and isinstance(actual, TInteger):
        return True
    return type(declared) is type(actual)


# ------------------------------------------------------------------------ V5 --


def v5_expressions(process: model.Process, ctx: TypeContext) -> list[Finding]:
    """An unparseable expression; an untyped path; an enum compared with a value
    outside it."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if isinstance(node, model.StepNode) and node.precondition:
            findings.extend(_check_expr(node.precondition, ctx, node_id))
        elif isinstance(node, model.RouteNode):
            for option in node.when:
                findings.extend(_check_expr(option.if_, ctx, node_id))
        elif isinstance(node, model.GateNode) and node.person_required_when:
            findings.extend(_check_expr(node.person_required_when, ctx, node_id))
    return findings


def _check_expr(text: str, ctx: TypeContext, node_id: str) -> list[Finding]:
    try:
        expr = parse(text)
        infer_type(expr, ctx)
    except DefinitionError as exc:
        return [Finding(rule="V5", node=node_id, message=f"{text!r}: {exc.message}")]
    return []


# ------------------------------------------------------------------------ V6 --


def v6_routes(process: model.Process, ctx: TypeContext) -> list[Finding]:
    """A route without `otherwise` that is not proven exhaustive."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if not isinstance(node, model.RouteNode) or node.otherwise is not None:
            continue
        if not _route_is_exhaustive(node, ctx):
            findings.append(
                Finding(
                    rule="V6",
                    node=node_id,
                    message=f"route {node_id!r} has no `otherwise` and is not proven exhaustive",
                    fix="add `otherwise`, or cover every value of the enum every option tests",
                )
            )
    return findings


def _route_is_exhaustive(node: model.RouteNode, ctx: TypeContext) -> bool:
    common_path: str | None = None
    covered: set[str] = set()
    enum_members: set[str] | None = None
    for option in node.when:
        try:
            expr = parse(option.if_)
        except DefinitionError:
            return False
        if not isinstance(expr, Compare) or expr.op != "==":
            return False
        left, right = expr.left, expr.right
        if (
            not isinstance(left, Path)
            or not isinstance(right, Literal)
            or not isinstance(right.value, str)
        ):
            return False
        path_key = str(left)
        if common_path is None:
            common_path = path_key
            try:
                left_type = ctx.resolve(left)
            except DefinitionError:
                return False
            if not isinstance(left_type, TEnum):
                return False
            enum_members = set(left_type.members)
        elif path_key != common_path:
            return False
        covered.add(right.value)
    return enum_members is not None and covered == enum_members


# ------------------------------------------------------------------------ V7 --


def _all_targets(node: model.Node) -> Iterator[tuple[str | None, str | None]]:
    """Yields (next_node_id, ending_name) for every way `node` can leave, from
    every branch it has (route options, on_error, on_control_fail, gate `on`, …)."""

    def target(rt: model.RouteTarget | None) -> Iterator[tuple[str | None, str | None]]:
        if rt is None:
            return
        yield rt.next, rt.end
        if rt.loop and rt.loop.on_exhausted:
            yield from target(rt.loop.on_exhausted)

    if isinstance(node, model.StepNode):
        yield node.next, node.end
        yield from target(node.on_forbidden)
        yield from target(node.on_precondition_false)
        yield from target(node.on_depth_exhausted)
        if node.on_control_fail:
            yield from target(node.on_control_fail.then)
        for rt in node.on_error.values():
            yield from target(rt)
    elif isinstance(node, model.RouteNode):
        for option in node.when:
            yield option.next, option.end
            if option.loop and option.loop.on_exhausted:
                yield from target(option.loop.on_exhausted)
        yield from target(node.otherwise)
    elif isinstance(node, model.ParallelNode):
        for branch in node.branches:
            yield branch, None
    elif isinstance(node, model.JoinNode):
        yield node.next, node.end
        yield from target(node.on_join_failed)
    elif isinstance(node, model.ForEachNode):
        yield node.do, None
        yield node.next, node.end
    elif isinstance(node, model.GateNode):
        for rt in node.on.values():
            yield from target(rt)


def v7_reachability(process: model.Process) -> list[Finding]:
    """An unreachable node; a node with no way to end."""

    findings: list[Finding] = []

    forward: dict[str, set[str]] = {nid: set() for nid in process.nodes}
    ends_directly: set[str] = set()
    for node_id, node in process.nodes.items():
        for next_id, end_name in _all_targets(node):
            if next_id and next_id in forward:
                forward[node_id].add(next_id)
            if end_name:
                ends_directly.add(node_id)
        if isinstance(node, model.ParallelNode) and node.join in process.nodes:
            forward[node_id].add(node.join)

    reachable = _bfs(process.start, forward)
    for node_id in process.nodes:
        if node_id != process.start and node_id not in reachable:
            findings.append(
                Finding(
                    rule="V7", node=node_id, message=f"node {node_id!r} is unreachable"
                )
            )

    reverse: dict[str, set[str]] = {nid: set() for nid in process.nodes}
    for node_id, targets in forward.items():
        for t in targets:
            reverse[t].add(node_id)
    can_end = set(ends_directly)
    frontier = set(ends_directly)
    while frontier:
        nxt = set()
        for n in frontier:
            for pred in reverse.get(n, ()):
                if pred not in can_end:
                    can_end.add(pred)
                    nxt.add(pred)
        frontier = nxt
    for node_id in process.nodes:
        if node_id not in can_end:
            findings.append(
                Finding(
                    rule="V7",
                    node=node_id,
                    message=f"node {node_id!r} has no way to end",
                )
            )
    return findings


def _bfs(start: str, graph: dict[str, set[str]]) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for n in frontier:
            for t in graph.get(n, ()):
                if t not in seen:
                    seen.add(t)
                    nxt.append(t)
        frontier = nxt
    return seen


# ------------------------------------------------------------------------ V8 --


def v8_loops(process: model.Process) -> list[Finding]:
    """A budget that is not a positive integer."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        for loop, where in _all_loops(node):
            if loop.budget is not None and (
                not isinstance(loop.budget, int) or loop.budget < 1
            ):
                findings.append(
                    Finding(
                        rule="V8",
                        node=node_id,
                        message=f"{where} has budget {loop.budget!r}, which is not a positive integer",
                    )
                )
    return findings


def _all_loops(node: model.Node) -> Iterator[tuple[model.LoopSpec, str]]:
    if isinstance(node, model.RouteNode):
        for option in node.when:
            if option.loop:
                yield option.loop, f"route option {option.if_!r}"
    elif (
        isinstance(node, model.StepNode)
        and node.on_control_fail
        and node.on_control_fail.then
        and node.on_control_fail.then.loop
    ):
        yield node.on_control_fail.then.loop, "on_control_fail.then"
    elif isinstance(node, model.GateNode):
        for verdict, rt in node.on.items():
            if rt.loop:
                yield rt.loop, f"on.{verdict}"


# ------------------------------------------------------------------------ V9 --

_KNOWN_GATE_KINDS = ("APPROVAL", "INPUT")


def v9_gates(process: model.Process, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if not isinstance(node, model.GateNode):
            continue
        findings.extend(_v9_one_gate(node_id, node, process, registry))
    return findings


def _producer_tool_ids(
    reviewing: tuple[str, ...], process: model.Process, registry: Registry
) -> set[str]:
    """Every Tool id whose STEP writes one of `reviewing`'s `state.*` paths —
    what an agent decider's "no deciding on your own work" check (spec §7.6,
    ANSI INCITS 359-2004 static separation of duty) needs to compare against."""

    channels = {p[len("state.") :] for p in reviewing if p.startswith("state.")}
    ids: set[str] = set()
    for node in process.nodes.values():
        if not isinstance(node, model.StepNode):
            continue
        writes_a_reviewed_channel = any(
            dest.startswith("state.") and dest[len("state.") :] in channels
            for dest in node.out.values()
        )
        if not writes_a_reviewed_channel:
            continue
        try:
            ids.add(registry.resolve("TOOL", node.tool).header.id)
        except DefinitionError:
            continue
    return ids


def _v9_one_gate(
    node_id: str, node: model.GateNode, process: model.Process, registry: Registry
) -> Iterator[Finding]:
    if not (node.asks or "").strip():
        yield Finding(
            rule="V9", node=node_id, message=f"gate {node_id!r} has no `asks`"
        )

    if node.kind not in _KNOWN_GATE_KINDS:
        yield Finding(
            rule="V9",
            node=node_id,
            message=f"gate {node_id!r} has unknown kind {node.kind!r}",
        )
        return  # the checks below assume a known kind

    if node.kind == "INPUT":
        # WP-03a Fault 2: `kind: INPUT` is spec-legal (§7.6) — schema and
        # model both already accept it — but the engine has never
        # implemented it (`_advance_gate` does not read `node.kind`,
        # `answer_type`, `answer_into`, or the `ANSWERED` verdict), so a
        # validated INPUT gate crashed at runtime instead of running: a
        # policy/agent/person decider's PERMIT/DENY answer, evaluated as
        # if this were an APPROVAL gate, has no route in `on` (INPUT gates
        # only ever declare `ANSWERED`), so the engine raised "no route
        # declared for verdict 'PERMIT'" — a confusing failure for a
        # definition that had already passed validation. Refused here
        # instead (D24, spec decision log): "an incomplete definition is
        # invalid, not a TODO" applies to engine support the same way it
        # applies to the definition's own shape. This is deliberately
        # unconditional — even an otherwise well-formed INPUT gate (a
        # real `answer_type`/`answer_into`, an `ANSWERED` route, no
        # `INDETERMINATE` route) is refused, since the gap is engine
        # support, not gate shape; the checks below (which are already
        # written INPUT-aware, ready for when support lands) are skipped
        # rather than run against a shape nothing can act on yet.
        yield Finding(
            rule="V9",
            node=node_id,
            message=(
                f"gate {node_id!r} declares kind INPUT, which this engine "
                "does not execute yet (see the spec's own decision log, D24) "
                "— refused rather than validating a definition it would "
                "crash on"
            ),
        )
        return

    if "INDETERMINATE" in node.on:
        yield Finding(
            rule="V9",
            node=node_id,
            message=f"gate {node_id!r} routes INDETERMINATE, which must pass on, not route",
        )

    # Only APPROVAL reaches here today (INPUT is refused above); this stays
    # a lookup rather than a bare tuple so it needs no change the day INPUT
    # support lands and rejoins this shared shape check.
    required_verdicts = {"APPROVAL": ("PERMIT", "DENY")}[node.kind]
    for verdict in required_verdicts:
        if verdict not in node.on:
            yield Finding(
                rule="V9",
                node=node_id,
                message=f"gate {node_id!r} has no route for {verdict}",
            )

    if node.person_required_when and not any(d.kind == "person" for d in node.deciders):
        yield Finding(
            rule="V9",
            node=node_id,
            message=f"gate {node_id!r} sets person_required_when but has no person decider",
        )

    for decider in node.deciders:
        if decider.kind != "agent":
            continue
        # _v2_process_references already reports an unresolved decider ref (V2);
        # skip silently here rather than reporting the same broken reference twice.
        tool, err = _resolve(registry, "TOOL", decider.ref)
        if err:
            continue
        if not any(o.type == "profile:decision@1" for o in tool.output.values()):
            yield Finding(
                rule="V9",
                node=node_id,
                message=f"gate {node_id!r}'s agent decider {decider.ref!r} does not return profile:decision@1",
            )
        producers = _producer_tool_ids(node.reviewing, process, registry)
        if tool.header.id in producers:
            yield Finding(
                rule="V9",
                node=node_id,
                message=(
                    f"gate {node_id!r}'s agent decider {decider.ref!r} would be reviewing its own output"
                ),
            )


# ------------------------------------------------------------------------ V10 --


def v10_calls(process: model.Process, registry: Registry) -> list[Finding]:
    findings: list[Finding] = []
    call_graph = _build_call_graph(registry)
    self_reachable = process.header.id in call_graph and _reaches(
        call_graph, process.header.id, process.header.id
    )

    for node_id, node in process.nodes.items():
        if not isinstance(node, model.StepNode):
            continue
        tool, err = _resolve(registry, "TOOL", node.tool)
        if err or tool is None or tool.mechanism.kind != "PROCESS":
            continue

        if tool.mechanism.result is not None:
            child, err = _resolve(registry, "PROCESS", tool.mechanism.ref)
            if child is not None:
                child_endings = set(child.endings) | set(_ENGINE_ENDINGS)
                mapped = set(tool.mechanism.result.endings)
                missing = child_endings - mapped
                if missing:
                    findings.append(
                        Finding(
                            rule="V10",
                            node=node_id,
                            message=f"call to {tool.mechanism.ref!r} does not map child ending(s): "
                            f"{sorted(missing)}",
                        )
                    )

        if self_reachable and node.on_depth_exhausted is None:
            findings.append(
                Finding(
                    rule="V10",
                    node=node_id,
                    message=f"process {process.header.id!r} can reach itself but step {node_id!r} "
                    "(a process call) has no on_depth_exhausted",
                )
            )
    return findings


def _build_call_graph(registry: Registry) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for proc in registry.all("PROCESS"):
        assert isinstance(
            proc, model.Process
        )  # registry.all("PROCESS", ...) guarantees this
        edges = graph.setdefault(proc.header.id, set())
        for node in proc.nodes.values():
            if not isinstance(node, model.StepNode):
                continue
            try:
                tool = registry.resolve("TOOL", node.tool)
            except DefinitionError:
                continue
            assert isinstance(
                tool, model.Tool
            )  # registry.resolve("TOOL", ...) guarantees this
            if tool.mechanism.kind == "PROCESS" and tool.mechanism.ref:
                try:
                    child = registry.resolve("PROCESS", tool.mechanism.ref)
                except DefinitionError:
                    continue
                edges.add(child.header.id)
    return graph


def _reaches(graph: dict[str, set[str]], start: str, target: str) -> bool:
    seen: set[str] = set()
    frontier = list(graph.get(start, ()))
    while frontier:
        nxt: list[str] = []
        for n in frontier:
            if n == target:
                return True
            if n not in seen:
                seen.add(n)
                nxt.extend(graph.get(n, ()))
        frontier = nxt
    return False


# ------------------------------------------------------------------------ V11 --


def v11_parallel(process: model.Process) -> list[Finding]:
    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if not isinstance(node, model.ParallelNode):
            continue
        writes_by_channel: dict[str, list[str]] = {}
        for branch in node.branches:
            for channel in _branch_state_writes(branch, node.join, process):
                writes_by_channel.setdefault(channel, []).append(branch)
            if not _bfs(branch, _forward_graph(process)).intersection({node.join}):
                findings.append(
                    Finding(
                        rule="V11",
                        node=node_id,
                        message=f"branch {branch!r} cannot reach join {node.join!r}",
                    )
                )
        for channel, branches in writes_by_channel.items():
            if len(branches) < 2:
                continue
            if (
                process.state.get(channel)
                and process.state[channel].reducer == "REPLACE"
            ):
                findings.append(
                    Finding(
                        rule="V11",
                        node=node_id,
                        message=f"branches {branches} both write state.{channel} (reducer REPLACE)",
                    )
                )
    return findings


def _forward_graph(process: model.Process) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {nid: set() for nid in process.nodes}
    for node_id, node in process.nodes.items():
        for next_id, _end in _all_targets(node):
            if next_id and next_id in graph:
                graph[node_id].add(next_id)
        if isinstance(node, model.ParallelNode) and node.join in process.nodes:
            graph[node_id].add(node.join)
    return graph


def _branch_state_writes(start: str, join: str, process: model.Process) -> set[str]:
    writes: set[str] = set()
    graph = _forward_graph(process)
    seen = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for n in frontier:
            node = process.nodes.get(n)
            if isinstance(node, model.StepNode):
                for dest in node.out.values():
                    if dest.startswith("state."):
                        writes.add(dest[len("state.") :])
            for t in graph.get(n, ()):
                if t != join and t not in seen:
                    seen.add(t)
                    nxt.append(t)
        frontier = nxt
    return writes


# ------------------------------------------------------------------------ V12 --


def v12_for_each(process: model.Process, ctx: TypeContext) -> list[Finding]:
    """`over` not list-typed."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if not isinstance(node, model.ForEachNode):
            continue
        over_type = _resolve_path_type(node.over, ctx)
        if over_type is not None and not isinstance(over_type, TList):
            findings.append(
                Finding(
                    rule="V12",
                    node=node_id,
                    message=f"for_each {node_id!r}: `over` ({node.over!r}) is {_type_repr(over_type)!r}, not a list",
                )
            )
    return findings


# ------------------------------------------------------------------------ V13 --


def v13_side_effects(process: model.Process) -> list[Finding]:
    """A destructive step with no precondition."""

    findings: list[Finding] = []
    for node_id, node in process.nodes.items():
        if (
            isinstance(node, model.StepNode)
            and node.destructive
            and not (node.precondition or "").strip()
        ):
            findings.append(
                Finding(
                    rule="V13",
                    node=node_id,
                    message=f"step {node_id!r} is destructive but has no precondition",
                )
            )
    return findings


# ------------------------------------------------------------------------ V14 --


def v14_endings(process: model.Process) -> list[Finding]:
    """An `end` naming an undeclared ending; an ending with no `says`."""

    findings: list[Finding] = []
    declared = set(process.endings) | set(_ENGINE_ENDINGS)
    for node_id, node in process.nodes.items():
        for _next_id, end_name in _all_targets(node):
            if end_name and end_name not in declared:
                findings.append(
                    Finding(
                        rule="V14",
                        node=node_id,
                        message=f"`end: {end_name}` names an undeclared ending",
                    )
                )
    for name, ending in process.endings.items():
        if not (ending.says or "").strip():
            findings.append(
                Finding(rule="V14", message=f"ending {name!r} has no `says`")
            )
    return findings


def v16_state_channels(process: model.Process) -> list[Finding]:
    """A channel declaring `reducer: UPSERT_BY_ID` with no `key` to upsert by
    (spec §2.3: "`UPSERT_BY_ID` (lists of objects, replaced by `key`)" — a
    channel that never names one is not that reducer's shape, whatever it
    calls itself). The schema (V1) leaves `key` optional on every reducer,
    since only `UPSERT_BY_ID` needs it; this rule closes that gap."""

    findings: list[Finding] = []
    for name, channel in process.state.items():
        if channel.reducer == "UPSERT_BY_ID" and not channel.key:
            findings.append(
                Finding(
                    rule="V16",
                    message=(
                        f"state channel {name!r} declares reducer UPSERT_BY_ID "
                        "with no `key`"
                    ),
                    fix="add `key: <field>` naming the object field to upsert by",
                )
            )
    return findings
