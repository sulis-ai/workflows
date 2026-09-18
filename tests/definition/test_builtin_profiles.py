"""The two built-in profiles the spec names (§5.2 control-result, §7.6 decision) ship
as loadable PROFILE documents so other definitions can reference `control-result@1`
and `decision@1` (WP-01 scope item 1)."""

from __future__ import annotations

from pathlib import Path

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.model import Profile

BUILTIN = Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition" / "builtin"


def test_control_result_profile_loads() -> None:
    profile = load_definition_file(BUILTIN / "control-result.profile.yaml")
    assert isinstance(profile, Profile)
    assert profile.header.id == "control-result"
    assert set(profile.schema["required"]) == {"control", "passed", "findings"}


def test_decision_profile_loads() -> None:
    profile = load_definition_file(BUILTIN / "decision.profile.yaml")
    assert isinstance(profile, Profile)
    assert profile.header.id == "decision"
    assert profile.schema["properties"]["verdict"]["enum"] == ["PERMIT", "DENY", "INDETERMINATE"]
