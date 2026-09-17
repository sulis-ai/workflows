"""V2 — reference resolution (spec §1.2): id@version and caret ranges."""

from __future__ import annotations

import pytest

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry, parse_ref


def _tool(id_: str, version: str) -> object:
    return load_definition(
        f"""
api_version: sulis.workflows/v1
kind: TOOL
id: {id_}
version: {version}
title: Echo
inputs: {{ value: {{ type: string }} }}
output: {{ value: {{ type: string }} }}
controls: [ {{ profile: finding@1 }} ]
mechanism: {{ kind: CODE, ref: "pkg.mod:fn" }}
effect: QUERY
""",
        fmt="yaml",
    )


# --------------------------------------------------------------------- parse_ref --


def test_parse_ref_accepts_exact_version() -> None:
    ref = parse_ref("grounded-inquiry@1.2.0")
    assert ref.id == "grounded-inquiry"
    assert ref.caret is False
    assert ref.version == (1, 2, 0)


def test_parse_ref_accepts_caret_range() -> None:
    ref = parse_ref("grounded-inquiry@^1.2")
    assert ref.caret is True
    assert ref.version == (1, 2)


def test_parse_ref_accepts_bare_partial_version() -> None:
    # spec §1.2, D11 — every reference in the spec is written this way (`tool@1`).
    ref = parse_ref("grounded-inquiry@1")
    assert ref.caret is False
    assert ref.version == (1,)


@pytest.mark.parametrize(
    "bad_ref",
    [
        "grounded-inquiry",  # no @version at all
        "grounded-inquiry@",  # empty version
        "GROUNDED_INQUIRY@1.0.0",  # id not kebab-case
        "grounded-inquiry@v1.0.0",  # not a bare number
    ],
)
def test_parse_ref_refuses_malformed_reference(bad_ref: str) -> None:
    with pytest.raises(DefinitionError) as excinfo:
        parse_ref(bad_ref)
    assert excinfo.value.rule == "V2"


# ----------------------------------------------------------------------- resolve --


def test_resolve_exact_version() -> None:
    registry = Registry([_tool("echo", "1.0.0"), _tool("echo", "1.1.0")])
    resolved = registry.resolve("TOOL", "echo@1.0.0")
    assert resolved.header.version == "1.0.0"


def test_resolve_caret_range_picks_highest_satisfying_version() -> None:
    registry = Registry(
        [_tool("echo", "1.0.0"), _tool("echo", "1.4.0"), _tool("echo", "2.0.0")]
    )
    resolved = registry.resolve("TOOL", "echo@^1.2")
    assert resolved.header.version == "1.4.0"


def test_resolve_bare_partial_version_matches_caret_of_same_precision() -> None:
    """spec §1.2, D11: `echo@1` and `echo@^1` resolve identically — every
    reference throughout this spec (`frame-question@1`, `insight@1`, ...) is
    written the bare way, so this is the form that has to work."""

    registry = Registry(
        [_tool("echo", "1.0.0"), _tool("echo", "1.4.0"), _tool("echo", "2.0.0")]
    )
    assert registry.resolve("TOOL", "echo@1").header.version == "1.4.0"
    assert registry.resolve("TOOL", "echo@1") is registry.resolve("TOOL", "echo@^1")


def test_resolve_full_bare_version_is_an_exact_pin_not_a_range() -> None:
    registry = Registry([_tool("echo", "1.0.0"), _tool("echo", "1.4.0")])
    assert registry.resolve("TOOL", "echo@1.0.0").header.version == "1.0.0"


@pytest.mark.parametrize(
    "requested,registered,expected",
    [
        ("^1.2.3", ["1.2.3", "1.9.9", "2.0.0"], "1.9.9"),
        ("^0.2.3", ["0.2.3", "0.2.9", "0.3.0"], "0.2.9"),
        ("^0.0.3", ["0.0.3", "0.0.4"], "0.0.3"),
        ("^0.0", ["0.0.0", "0.0.9", "0.1.0"], "0.0.9"),
        ("^0", ["0.9.9", "1.0.0"], "0.9.9"),
    ],
)
def test_caret_bounds_match_node_semver(
    requested: str, registered: list[str], expected: str
) -> None:
    registry = Registry([_tool("echo", v) for v in registered])
    resolved = registry.resolve("TOOL", f"echo@{requested}")
    assert resolved.header.version == expected


def test_unregistered_id_is_refused() -> None:
    registry = Registry([_tool("echo", "1.0.0")])
    with pytest.raises(DefinitionError) as excinfo:
        registry.resolve("TOOL", "nonexistent@1.0.0")
    assert excinfo.value.rule == "V2"


def test_unregistered_exact_version_is_refused() -> None:
    registry = Registry([_tool("echo", "1.0.0")])
    with pytest.raises(DefinitionError) as excinfo:
        registry.resolve("TOOL", "echo@2.0.0")
    assert excinfo.value.rule == "V2"
    assert "1.0.0" in str(excinfo.value)  # names what IS registered


def test_caret_range_with_no_satisfying_version_is_refused() -> None:
    registry = Registry([_tool("echo", "1.0.0")])
    with pytest.raises(DefinitionError) as excinfo:
        registry.resolve("TOOL", "echo@^2.0")
    assert excinfo.value.rule == "V2"


def test_wrong_kind_is_refused_even_if_id_registered_under_another_kind() -> None:
    registry = Registry([_tool("echo", "1.0.0")])
    with pytest.raises(DefinitionError):
        registry.resolve("CONTROL", "echo@1.0.0")


def test_malformed_reference_is_refused_before_any_lookup() -> None:
    registry = Registry([_tool("echo", "1.0.0")])
    with pytest.raises(DefinitionError) as excinfo:
        registry.resolve("TOOL", "not-even-a-reference")
    assert excinfo.value.rule == "V2"
