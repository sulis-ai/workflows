"""check_controls (spec §10.2) — the checkable subset (WP-02 step 2).

Only `profile:` controls have a dispatch path today (checkers.profile_conformance,
called directly since it is this library's own code). Everything else must
come back unsupported/uncheckable — fail closed, never silently trusted.
"""

from __future__ import annotations

from sulis_workflows.definition.model import (
    ControlRef,
    Header,
    Mechanism,
    OutputSpec,
    Profile,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.engine.controls import check_controls


def _header(id_: str, kind: str) -> Header:
    return Header(
        api_version="sulis.workflows/v1", kind=kind, id=id_, version="1.0.0", title=id_
    )


def _insight_profile() -> Profile:
    return Profile(
        header=_header("insight", "PROFILE"),
        schema={
            "type": "object",
            "required": ["id", "claim"],
            "properties": {"id": {"type": "string"}, "claim": {"type": "string"}},
            "additionalProperties": False,
        },
    )


def _tool_with_bare_profile_output() -> Tool:
    return Tool(
        header=_header("conclude", "TOOL"),
        output={"insight": OutputSpec(type="profile:insight@1")},
        controls=(ControlRef(kind="profile", ref="insight@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )


def _tool_with_list_profile_output() -> Tool:
    return Tool(
        header=_header("interrogate", "TOOL"),
        output={"insights": OutputSpec(type="list<profile:insight@1>")},
        controls=(ControlRef(kind="profile", ref="insight@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )


def test_bare_profile_output_that_conforms_passes():
    registry = Registry([_insight_profile()])
    tool = _tool_with_bare_profile_output()
    result = check_controls(
        tool, {"insight": {"id": "i1", "claim": "x"}}, registry=registry
    )
    assert result.checkable
    assert result.all_passed
    assert len(result.outcomes) == 1


def test_bare_profile_output_that_fails_schema_is_reported():
    registry = Registry([_insight_profile()])
    tool = _tool_with_bare_profile_output()
    result = check_controls(
        tool, {"insight": {"id": "i1"}}, registry=registry
    )  # missing claim
    assert result.checkable
    assert not result.all_passed
    assert result.outcomes[0].findings


def test_list_profile_output_checks_every_item():
    registry = Registry([_insight_profile()])
    tool = _tool_with_list_profile_output()
    output = {
        "insights": [
            {"id": "i1", "claim": "good"},
            {"id": "i2"},  # missing claim — should fail
        ]
    }
    result = check_controls(tool, output, registry=registry)
    assert result.checkable
    assert len(result.outcomes) == 2
    assert result.outcomes[0].passed
    assert not result.outcomes[1].passed
    assert not result.all_passed


def test_conventions_control_is_unsupported_not_silently_passed():
    tool = Tool(
        header=_header("interrogate", "TOOL"),
        output={"verdict": OutputSpec(type="string")},
        controls=(ControlRef(kind="conventions", ref="faithful-generation@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    result = check_controls(tool, {"verdict": "ok"}, registry=Registry([]))
    assert not result.checkable
    assert not result.all_passed
    assert result.unsupported == (
        ControlRef(kind="conventions", ref="faithful-generation@1"),
    )


def test_policy_control_is_unsupported_not_silently_passed():
    tool = Tool(
        header=_header("interrogate", "TOOL"),
        output={"verdict": OutputSpec(type="string")},
        controls=(ControlRef(kind="policy", ref="some-policy@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    result = check_controls(tool, {"verdict": "ok"}, registry=Registry([]))
    assert not result.checkable


def test_a_profile_control_matching_no_output_field_is_unsupported():
    tool = Tool(
        header=_header("conclude", "TOOL"),
        output={
            "insight": OutputSpec(type="string")
        },  # doesn't declare profile:insight@1
        controls=(ControlRef(kind="profile", ref="insight@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    result = check_controls(
        tool, {"insight": "not a profile value"}, registry=Registry([])
    )
    assert not result.checkable


def test_a_fully_uncheckable_tool_with_no_controls_at_all_is_trivially_checkable():
    # No controls declared -> nothing unsupported -> vacuously checkable and passed.
    # (V3 refuses a Tool with zero controls at validation time; this is a runtime unit
    # test of check_controls in isolation, not a claim that such a Tool is valid.)
    tool = Tool(
        header=_header("noop", "TOOL"),
        output={"x": OutputSpec(type="string")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    result = check_controls(tool, {"x": "y"}, registry=Registry([]))
    assert result.checkable
    assert result.all_passed
