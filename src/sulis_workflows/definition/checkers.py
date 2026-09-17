"""The two built-in checkers spec §5.2/§7.6 name, as `CODE` Tools. Both are pure
functions of their arguments (the mechanism the format itself requires of a
checker, §5.2: "A checker is a `CODE` Tool") and return `profile:control-result@1`
(`{ control, passed, findings }`). Their Tool definitions ship alongside them —
`builtin/profile-conformance.tool.yaml`, `builtin/decision-evidence.tool.yaml` —
each with `mechanism.ref` naming the function here it wraps.

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from jsonschema.validators import Draft202012Validator

from sulis_workflows.definition.model import Profile
from sulis_workflows.definition.registry import Registry

__all__ = ["decision_evidence", "profile_conformance"]


def profile_conformance(
    value: Any, control: str, *, registry: Registry
) -> dict[str, Any]:
    """The checker every `profile:` control uses (spec §5.2): validates `value`
    against the JSON Schema of the Profile `control` names (an `id@version`
    reference, e.g. `"finding@1"`)."""

    profile = registry.resolve("PROFILE", control)
    assert isinstance(
        profile, Profile
    )  # registry.resolve("PROFILE", ...) guarantees this
    validator = Draft202012Validator(profile.schema)
    findings = [
        {
            "path": "/".join(str(p) for p in error.absolute_path) or "(root)",
            "message": error.message,
            "severity": "ERROR",
        }
        for error in validator.iter_errors(value)
    ]
    return {"control": control, "passed": not findings, "findings": findings}


def decision_evidence(
    value: Mapping[str, Any], control: str, reviewing: Sequence[str]
) -> dict[str, Any]:
    """The `decision@1` evidence checker (spec §7.6): every `evidence[].path`
    must be one of the gate's `reviewing` paths. Checks membership only — spec
    §7.6 also asks that each path "resolve to a value in the run", which needs
    live run state this checker is never given; that half is an engine-time
    concern, out of WP-01's scope (its own "Out of scope" section names the
    engine as later work), and is left for whoever builds it."""

    reviewing_set = set(reviewing)
    findings = []
    for index, item in enumerate(value.get("evidence", [])):
        path = item.get("path") if isinstance(item, Mapping) else None
        if path not in reviewing_set:
            findings.append(
                {
                    "path": f"evidence[{index}].path",
                    "message": f"{path!r} is not one of the gate's reviewing paths {sorted(reviewing_set)}",
                    "severity": "ERROR",
                }
            )
    return {"control": control, "passed": not findings, "findings": findings}
