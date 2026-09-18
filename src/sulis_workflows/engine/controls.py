"""Controls-after-every-step — the checkable subset (spec §10.2, WP-02 step 2).

§4.4: "Every non-policy control MUST have a registered checker." §10.2 then
runs that checker after every step. `profile:` controls are checked with
WP-01's built-in ``profile_conformance`` (spec §5.2) directly — it is this
library's own code (``definition/checkers.py``), not host-provided, the
same reason WP-01's own CLI calls it directly rather than through a port.

`conventions:`/`fitness:` controls name a checker Tool on their own Control
document (`checker: <tool-ref>`, spec §5.1/§5.2's "a checker is a CODE
Tool") and are dispatched through the same `CodeToolPort` a STEP's own
Tool uses (mirrors §12.1's CODE/EXTERNAL/deterministic-PROCESS vs.
SKILL/non-deterministic-PROCESS split — a checker is always CODE, so
there is no hand-off case to invent here). This was deferred past WP-02 step 2 itself ("no
fixture yet exercises it" — this module's own prior docstring) until a
live run of the spec's own Appendix A worked example actually needed it:
nearly every one of its Tools uses a `conventions:` control, so without
this every one of those steps would fail closed as `CONTROLS_UNCHECKABLE`
before ever reaching its own logic.

`policy:` controls (a STEP's own output checked against a named policy,
distinct from a GATE's `policy:` decider) still have no dispatch path —
no fixture in this repository declares one, and inventing dispatch for a
shape nothing exercises would be exactly the speculative guess this
module's docstring has always warned against; still `unsupported`,
fail-closed, same as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sulis_workflows.definition import checkers
from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.expressions import TList, TProfile, parse_type
from sulis_workflows.definition.model import Control, ControlRef, Tool
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.code_tool import (
    CodeToolPort,
    ToolPermanentError,
    ToolTransientError,
)

__all__ = ["ControlOutcome", "ControlsResult", "check_controls"]


@dataclass(frozen=True)
class ControlOutcome:
    """One checker's verdict on one output value (or list item)."""

    control: ControlRef
    passed: bool
    findings: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ControlsResult:
    """Every checkable control's outcome, plus what this engine could not check.

    ``checkable`` is False whenever ``unsupported`` is non-empty — the step
    MUST NOT be treated as passed on the strength of ``outcomes`` alone in
    that case; there is no partial trust here.
    """

    outcomes: tuple[ControlOutcome, ...] = ()
    unsupported: tuple[ControlRef, ...] = ()

    @property
    def checkable(self) -> bool:
        return not self.unsupported

    @property
    def all_passed(self) -> bool:
        return self.checkable and all(o.passed for o in self.outcomes)


async def check_controls(
    tool: Tool,
    output: Mapping[str, Any],
    *,
    registry: Registry,
    code_tool: CodeToolPort,
    platform_id: str,
    run_id: str,
) -> ControlsResult:
    """Check every control this engine can dispatch: `profile:` (inline,
    §5.2's built-in checker) and `conventions:`/`fitness:` (their own
    named checker Tool, dispatched via `CodeToolPort`). `policy:` controls
    on a STEP still have no dispatch path — see module docstring.

    A `profile: X@v` control is matched to whichever output field(s)
    declare that profile in their type — bare `profile:X@v` (checked
    once, on the field's value) or `list<profile:X@v>` (checked once per
    item). A `conventions:`/`fitness:` control is checked once, against
    whatever its own `applies_to` names (`output` — the whole output
    mapping — or `output.<field>` — one field's value); unlike `profile:`
    it is never matched against output *types*, since `applies_to` already
    says exactly what it means to check. A profile control matching no
    output field, a conventions/fitness control this engine cannot
    resolve or whose checker itself fails to run, and any `policy:`
    control, all land in ``unsupported``.
    """
    outcomes: list[ControlOutcome] = []
    unsupported: list[ControlRef] = []

    for control in tool.controls:
        if control.kind == "profile":
            matched = False
            for field_name, output_spec in tool.output.items():
                parsed = parse_type(output_spec.type)
                value = output.get(field_name)

                if isinstance(parsed, TProfile) and parsed.ref == control.ref:
                    matched = True
                    outcomes.append(_check_profile(control, value, registry))
                elif (
                    isinstance(parsed, TList)
                    and isinstance(parsed.item, TProfile)
                    and parsed.item.ref == control.ref
                ):
                    matched = True
                    for item in value if isinstance(value, list) else []:
                        outcomes.append(_check_profile(control, item, registry))

            if not matched:
                unsupported.append(control)
            continue

        if control.kind in ("conventions", "fitness"):
            outcome = await _check_dispatchable(
                control,
                output,
                registry=registry,
                code_tool=code_tool,
                platform_id=platform_id,
                run_id=run_id,
            )
            if outcome is None:
                unsupported.append(control)
            else:
                outcomes.append(outcome)
            continue

        unsupported.append(control)  # `policy:` — no dispatch path yet

    return ControlsResult(outcomes=tuple(outcomes), unsupported=tuple(unsupported))


def _check_profile(
    control: ControlRef, value: Any, registry: Registry
) -> ControlOutcome:
    result = checkers.profile_conformance(value, control.ref, registry=registry)
    return ControlOutcome(
        control=control,
        passed=result["passed"],
        findings=tuple(result["findings"]),
    )


def _applies_to_value(applies_to: str, output: Mapping[str, Any]) -> Any:
    if applies_to == "output":
        return dict(output)
    if applies_to.startswith("output."):
        return output.get(applies_to[len("output.") :])
    return None  # an unrecognised path shape — caller treats as unsupported


async def _check_dispatchable(
    control: ControlRef,
    output: Mapping[str, Any],
    *,
    registry: Registry,
    code_tool: CodeToolPort,
    platform_id: str,
    run_id: str,
) -> ControlOutcome | None:
    """Dispatches one `conventions:`/`fitness:` control's own checker Tool.
    Returns `None` (caller marks the control `unsupported`, fail-closed)
    when the Control document, its `checker`/`applies_to`, or the checker
    Tool itself cannot be resolved, or the checker's own dispatch fails —
    never raises, since one uncheckable control must not crash the run.
    """
    try:
        control_doc = registry.resolve("CONTROL", control.ref)
    except DefinitionError:
        return None
    if (
        not isinstance(control_doc, Control)
        or control_doc.checker is None
        or control_doc.applies_to is None
    ):
        return None

    try:
        checker_tool = registry.resolve("TOOL", control_doc.checker)
    except DefinitionError:
        return None
    if not isinstance(checker_tool, Tool) or checker_tool.mechanism.kind != "CODE":
        return None

    value = _applies_to_value(control_doc.applies_to, output)

    ref = checker_tool.mechanism.ref
    assert ref is not None  # V1 requires a CODE mechanism to declare `ref`
    try:
        raw = await code_tool.call(
            ref,
            {"value": value, "control": control.ref},
            platform_id=platform_id,
            run_id=run_id,
        )
    except (ToolTransientError, ToolPermanentError):
        return None

    payload = raw.get("result")
    if not isinstance(payload, Mapping):
        return None
    return ControlOutcome(
        control=control,
        passed=bool(payload.get("passed")),
        findings=tuple(payload.get("findings", ())),
    )
