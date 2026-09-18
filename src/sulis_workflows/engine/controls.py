"""Controls-after-every-step — the checkable subset (spec §10.2, WP-02 step 2).

§4.4: "Every non-policy control MUST have a registered checker." §10.2 then
runs that checker after every step. This engine can currently only *call*
one checker: WP-01's built-in ``profile_conformance`` (spec §5.2), because
it is this library's own code (``definition/checkers.py``), not
host-provided — the same reason WP-01's own CLI calls it directly rather
than through a port.

``conventions:``/``fitness:`` controls (a custom checker Tool a Control
document names) and ``policy:`` controls have no dispatch path here yet:
no such checker exists as a callable anywhere in this repository today
(only the two WP-01 built-ins do, and the second — ``decision_evidence`` —
is §7.6's gate evidence checker, used by GATE execution, not a STEP
control). Building generic dispatch for controls no fixture yet exercises
would be speculative; the honest, fail-closed choice is to say so and
refuse rather than silently trust an unchecked control (§4.4's own rule
for an unresolved control, applied here to an uncheckable one).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sulis_workflows.definition import checkers
from sulis_workflows.definition.expressions import TList, TProfile, parse_type
from sulis_workflows.definition.model import ControlRef, Tool
from sulis_workflows.definition.registry import Registry

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


def check_controls(
    tool: Tool, output: Mapping[str, Any], *, registry: Registry
) -> ControlsResult:
    """Check every `profile:` control this engine can dispatch.

    A `profile: X@v` control is matched to whichever output field(s)
    declare that profile in their type — bare `profile:X@v` (checked
    once, on the field's value) or `list<profile:X@v>` (checked once per
    item). A profile control matching no output field, and any
    non-profile control, lands in ``unsupported``.
    """
    outcomes: list[ControlOutcome] = []
    unsupported: list[ControlRef] = []

    for control in tool.controls:
        if control.kind != "profile":
            unsupported.append(control)
            continue

        matched = False
        for field_name, output_spec in tool.output.items():
            parsed = parse_type(output_spec.type)
            value = output.get(field_name)

            if isinstance(parsed, TProfile) and parsed.ref == control.ref:
                matched = True
                outcomes.append(_check_one(control, value, registry))
            elif (
                isinstance(parsed, TList)
                and isinstance(parsed.item, TProfile)
                and parsed.item.ref == control.ref
            ):
                matched = True
                for item in value if isinstance(value, list) else []:
                    outcomes.append(_check_one(control, item, registry))

        if not matched:
            unsupported.append(control)

    return ControlsResult(outcomes=tuple(outcomes), unsupported=tuple(unsupported))


def _check_one(control: ControlRef, value: Any, registry: Registry) -> ControlOutcome:
    result = checkers.profile_conformance(value, control.ref, registry=registry)
    return ControlOutcome(
        control=control,
        passed=result["passed"],
        findings=tuple(result["findings"]),
    )
