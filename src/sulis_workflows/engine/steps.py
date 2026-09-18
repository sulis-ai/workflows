"""STEP execution — the CODE mechanism-kind path (spec §7.1, §10, §12.4, WP-02 step 2).

Scope note: only `CODE`-kind Tools (deterministic, "a function the host can
call", §4.3) are dispatched here. `SKILL`/`AGENTIC` Tools are
non-deterministic and are handed to the caller as a `TOOL_STEP` by
`next()` instead of run here (§12.1); `EXTERNAL`, deterministic `PROCESS`
and the `TOOL` composite mechanism follow in a later step, alongside
`next()`/`report()` itself — that is where the engine's dispatch-or-defer
decision actually lives (`docs/work-packages/WP-02-execution-engine.md`).

``attempt_step`` does exactly one attempt and reports what happened; it
does not retry, does not repair, and does not write anything into state or
records. Retrying (§12.4), repairing (§10.2 step 5) and recording (§12.2)
all need the attempt history `RecordsPort` holds — that is the caller's
job (`next()`/`report()`, WP-02 step 5), not this function's, so this
stays a pure, easily-tested unit.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sulis_workflows.definition.expressions import evaluate, parse
from sulis_workflows.definition.model import StepNode, Tool
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.code_tool import (
    CodeToolPort,
    ToolPermanentError,
    ToolTransientError,
)
from sulis_workflows.domain.ports.policy import PolicyPort, Verdict
from sulis_workflows.engine.controls import ControlsResult, check_controls

__all__ = [
    "ENGINE_INPUT_UNRESOLVED",
    "StepAttemptResult",
    "StepOutcome",
    "attempt_step",
]

ENGINE_INPUT_UNRESOLVED = "ENGINE_INPUT_UNRESOLVED"
"""Not one of the Tool's own declared error codes (§4.6) — this is the engine
failing to resolve a required input at runtime despite V4 guaranteeing it
was mapped, e.g. every declared path was absent. An engine-level structural
failure, not a business error the Tool author named."""


class StepOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FORBIDDEN = "FORBIDDEN"
    PRECONDITION_FALSE = "PRECONDITION_FALSE"
    INPUT_UNRESOLVED = "INPUT_UNRESOLVED"
    NOT_DISPATCHABLE = "NOT_DISPATCHABLE"
    CONTROLS_UNCHECKABLE = "CONTROLS_UNCHECKABLE"
    CONTROL_FAILED = "CONTROL_FAILED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class StepAttemptResult:
    """What happened when this attempt was made — never a route decision.

    ``next``/``report`` (WP-02 step 5) turn this into an actual routing
    decision (`on_forbidden`, `on_precondition_false`, `on_error`,
    `on_control_fail`, or `next`), using the node's own declared routes —
    this module knows nothing about node-to-node routing.
    """

    outcome: StepOutcome
    output: Mapping[str, Any] | None = None
    controls: ControlsResult | None = None
    error_code: str | None = None
    error_class: str | None = None  # "TRANSIENT" | "PERMANENT"
    rationale: str | None = None


async def attempt_step(
    node: StepNode,
    tool: Tool,
    run_state: Mapping[str, Any],
    *,
    identity: str,
    platform_id: str,
    run_id: str,
    policy: PolicyPort,
    code_tool: CodeToolPort,
    registry: Registry,
) -> StepAttemptResult:
    """Permission, then precondition, then inputs, then dispatch, then controls —
    in that order, matching §10's own ordering ("permission, then controls")
    extended with the two runtime gates §7.1 places before dispatch.
    """
    if tool.permission is None:
        return StepAttemptResult(
            outcome=StepOutcome.FORBIDDEN,
            rationale=(
                f"Tool {tool.header.id!r} declares no `permission` — refusing to "
                "dispatch rather than skip the check (spec §10.1, D12)."
            ),
        )

    decision = await policy.authorize(
        tool.permission, identity=identity, platform_id=platform_id, run_id=run_id
    )
    if decision.verdict != Verdict.PERMIT:
        return StepAttemptResult(
            outcome=StepOutcome.FORBIDDEN, rationale=decision.rationale
        )

    if node.precondition is not None and not evaluate(
        parse(node.precondition), run_state
    ):
        return StepAttemptResult(outcome=StepOutcome.PRECONDITION_FALSE)

    resolved_inputs, missing = _resolve_inputs(node.in_, tool, run_state)
    if missing:
        return StepAttemptResult(
            outcome=StepOutcome.INPUT_UNRESOLVED,
            error_code=ENGINE_INPUT_UNRESOLVED,
            error_class="PERMANENT",
            rationale=f"no present, non-empty value for required input(s): {', '.join(missing)}",
        )

    if tool.mechanism.kind != "CODE":
        return StepAttemptResult(
            outcome=StepOutcome.NOT_DISPATCHABLE,
            rationale=(
                f"mechanism kind {tool.mechanism.kind!r} is not yet executable by "
                "this engine (WP-02 step 2 handles CODE only)."
            ),
        )

    ref = tool.mechanism.ref
    assert ref is not None  # schema/V1 requires a CODE mechanism to declare `ref`

    try:
        output = await code_tool.call(
            ref, resolved_inputs, platform_id=platform_id, run_id=run_id
        )
    except (ToolTransientError, ToolPermanentError) as exc:
        return StepAttemptResult(
            outcome=StepOutcome.ERROR,
            error_code=exc.code,
            error_class=_classify(tool, exc.code),
            rationale=str(exc),
        )

    controls_result = await check_controls(
        tool,
        output,
        registry=registry,
        code_tool=code_tool,
        platform_id=platform_id,
        run_id=run_id,
    )
    if not controls_result.checkable:
        names = ", ".join(f"{c.kind}:{c.ref}" for c in controls_result.unsupported)
        return StepAttemptResult(
            outcome=StepOutcome.CONTROLS_UNCHECKABLE,
            output=output,
            controls=controls_result,
            rationale=f"this engine cannot yet check: {names}",
        )

    if not controls_result.all_passed:
        return StepAttemptResult(
            outcome=StepOutcome.CONTROL_FAILED, output=output, controls=controls_result
        )

    return StepAttemptResult(
        outcome=StepOutcome.SUCCESS, output=output, controls=controls_result
    )


def _classify(tool: Tool, code: str) -> str:
    """§4.6: "An unlisted error is PERMANENT." The Tool's own declared
    `errors[]` is authoritative over whichever exception type the adapter
    happened to raise."""
    for error_spec in tool.errors:
        if error_spec.code == code:
            return error_spec.error_class
    return "PERMANENT"


def _resolve_inputs(
    in_map: Mapping[str, str | list[str]],
    tool: Tool,
    run_state: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """§7.1: "every required Tool input MUST be mapped, to a path or an
    ordered list of paths (the first present, non-empty value is used)."""
    resolved: dict[str, Any] = {}
    missing: list[str] = []

    for name, input_spec in tool.inputs.items():
        paths = in_map.get(name)
        if paths is None:
            if input_spec.has_default:
                resolved[name] = input_spec.default
            elif input_spec.required:
                missing.append(name)
            continue

        path_list = [paths] if isinstance(paths, str) else list(paths)
        value = _first_present(path_list, run_state)
        if value is None:
            if input_spec.has_default:
                resolved[name] = input_spec.default
            elif input_spec.required:
                missing.append(name)
            continue
        resolved[name] = value

    return resolved, missing


def _first_present(paths: list[str], run_state: Mapping[str, Any]) -> Any:
    for path in paths:
        value = evaluate(parse(path), run_state)
        if value is None:
            continue
        if isinstance(value, (str, list, dict)) and len(value) == 0:
            continue
        return value
    return None
