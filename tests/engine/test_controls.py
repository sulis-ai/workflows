"""check_controls (spec §10.2) — the checkable subset (WP-02 step 2, extended
this session to dispatch `conventions:`/`fitness:` controls too).

`profile:` controls are checked with checkers.profile_conformance, called
directly since it is this library's own code. `conventions:`/`fitness:`
controls are dispatched via `CodeToolPort` to their own Control document's
named checker Tool. `policy:` controls (on a STEP) still have no dispatch
path and must come back unsupported/uncheckable — fail closed, never
silently trusted, same as any control this engine cannot resolve.
"""

from __future__ import annotations

import asyncio

from sulis_workflows.definition.model import (
    Control,
    ControlRef,
    Header,
    Mechanism,
    OutputSpec,
    Profile,
    Tool,
)
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.code_tool import (
    StubCodeToolAdapter,
    ToolPermanentError,
)
from sulis_workflows.engine.controls import check_controls


def _run(coro):
    return asyncio.run(coro)


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


def _check(tool, output, *, registry, code_tool=None):
    return _run(
        check_controls(
            tool,
            output,
            registry=registry,
            code_tool=code_tool or StubCodeToolAdapter(),
            platform_id="tenant-1",
            run_id="run-1",
        )
    )


def test_bare_profile_output_that_conforms_passes():
    registry = Registry([_insight_profile()])
    tool = _tool_with_bare_profile_output()
    result = _check(tool, {"insight": {"id": "i1", "claim": "x"}}, registry=registry)
    assert result.checkable
    assert result.all_passed
    assert len(result.outcomes) == 1


def test_bare_profile_output_that_fails_schema_is_reported():
    registry = Registry([_insight_profile()])
    tool = _tool_with_bare_profile_output()
    result = _check(tool, {"insight": {"id": "i1"}}, registry=registry)  # missing claim
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
    result = _check(tool, output, registry=registry)
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
    result = _check(tool, {"verdict": "ok"}, registry=Registry([]))
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
    result = _check(tool, {"verdict": "ok"}, registry=Registry([]))
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
    result = _check(tool, {"insight": "not a profile value"}, registry=Registry([]))
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
    result = _check(tool, {"x": "y"}, registry=Registry([]))
    assert result.checkable
    assert result.all_passed


def _output_present_control_and_checker() -> tuple[Control, Tool]:
    control = Control(
        header=_header("output-present", "CONTROL"),
        type="CONVENTIONS",
        applies_to="output",
        checker="output-present@1",
    )
    checker_tool = Tool(
        header=_header("output-present", "TOOL"),
        output={"result": OutputSpec(type="profile:control-result@1")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="checkers:output_present"),
        effect="QUERY",
    )
    return control, checker_tool


def test_conventions_control_with_a_resolvable_checker_dispatches_and_passes():
    """The gap this session closed: `conventions:`/`fitness:` controls now
    actually reach their own checker Tool via `CodeToolPort`, instead of
    always landing in `unsupported` regardless of whether a checker
    exists — this is the positive case proving dispatch really happens."""
    control, checker_tool = _output_present_control_and_checker()
    registry = Registry([control, checker_tool])
    tool = Tool(
        header=_header("frame", "TOOL"),
        output={"framed_question": OutputSpec(type="string")},
        controls=(ControlRef(kind="conventions", ref="output-present@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    code_tool = StubCodeToolAdapter(
        responses={
            "checkers:output_present": {
                "result": {
                    "control": "output-present@1",
                    "passed": True,
                    "findings": [],
                }
            }
        }
    )
    result = _check(
        tool,
        {"framed_question": "why?"},
        registry=registry,
        code_tool=code_tool,
    )
    assert result.checkable
    assert result.all_passed
    assert result.outcomes[0].control == ControlRef(
        kind="conventions", ref="output-present@1"
    )


def test_conventions_control_with_a_resolvable_checker_dispatches_and_fails():
    control, checker_tool = _output_present_control_and_checker()
    registry = Registry([control, checker_tool])
    tool = Tool(
        header=_header("frame", "TOOL"),
        output={"framed_question": OutputSpec(type="string")},
        controls=(ControlRef(kind="conventions", ref="output-present@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    code_tool = StubCodeToolAdapter(
        responses={
            "checkers:output_present": {
                "result": {
                    "control": "output-present@1",
                    "passed": False,
                    "findings": [
                        {
                            "path": "framed_question",
                            "message": "absent",
                            "severity": "ERROR",
                        }
                    ],
                }
            }
        }
    )
    result = _check(
        tool,
        {"framed_question": None},
        registry=registry,
        code_tool=code_tool,
    )
    assert result.checkable  # the checker DID run — it just found a problem
    assert not result.all_passed
    assert result.outcomes[0].findings


def test_conventions_control_whose_checker_dispatch_fails_is_unsupported():
    """A checker that itself errors must not crash the run or count as
    passed — one uncheckable control fails closed, the same as one this
    engine cannot resolve at all."""
    control, checker_tool = _output_present_control_and_checker()
    registry = Registry([control, checker_tool])
    tool = Tool(
        header=_header("frame", "TOOL"),
        output={"framed_question": OutputSpec(type="string")},
        controls=(ControlRef(kind="conventions", ref="output-present@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    code_tool = StubCodeToolAdapter(
        raises={"checkers:output_present": ToolPermanentError("BROKEN")}
    )
    result = _check(
        tool,
        {"framed_question": "why?"},
        registry=registry,
        code_tool=code_tool,
    )
    assert not result.checkable
    assert result.unsupported == (
        ControlRef(kind="conventions", ref="output-present@1"),
    )


def test_conventions_control_applies_to_a_single_output_field():
    control = Control(
        header=_header("faithful-generation", "CONTROL"),
        type="CONVENTIONS",
        applies_to="output.insights",
        checker="check-entailment@1",
    )
    checker_tool = Tool(
        header=_header("check-entailment", "TOOL"),
        output={"result": OutputSpec(type="profile:control-result@1")},
        controls=(),
        mechanism=Mechanism(kind="CODE", ref="checkers:check_entailment"),
        effect="QUERY",
    )
    registry = Registry([control, checker_tool])
    tool = Tool(
        header=_header("interrogate", "TOOL"),
        output={
            "insights": OutputSpec(type="list<profile:insight@1>"),
            "verdict": OutputSpec(type="string"),
        },
        controls=(ControlRef(kind="conventions", ref="faithful-generation@1"),),
        mechanism=Mechanism(kind="CODE", ref="mod:fn"),
        effect="QUERY",
    )
    seen: dict[str, object] = {}

    class RecordingCodeTool(StubCodeToolAdapter):
        async def call(self, ref, inputs, *, platform_id, run_id):
            seen["value"] = inputs["value"]
            return await super().call(
                ref, inputs, platform_id=platform_id, run_id=run_id
            )

    code_tool = RecordingCodeTool(
        responses={
            "checkers:check_entailment": {
                "result": {
                    "control": "faithful-generation@1",
                    "passed": True,
                    "findings": [],
                }
            }
        }
    )
    result = _check(
        tool,
        {"insights": [{"id": "i1", "claim": "c"}], "verdict": "SURVIVED"},
        registry=registry,
        code_tool=code_tool,
    )
    assert result.checkable
    assert result.all_passed
    # `applies_to: output.insights` must pass only that field's value, not
    # the whole output mapping — proves the path is actually followed, not
    # just that dispatch happens at all.
    assert seen["value"] == [{"id": "i1", "claim": "c"}]
