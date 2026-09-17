"""WP-01 A2: spec Appendix A (grounded-inquiry) validates once fixtures exist for
every Tool, Profile and Control it references; removing any one of them makes
V2 refuse it."""

from __future__ import annotations

from pathlib import Path

import pytest

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import validate_definition

BUILTIN = (
    Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition" / "builtin"
)
CORPUS = Path(__file__).parent / "fixtures" / "appendix_a_corpus"
APPENDIX_A = Path(__file__).parent / "fixtures" / "accepted" / "process-appendix-a.yaml"

_BUILTIN_FILES = [
    BUILTIN / "control-result.profile.yaml",
    BUILTIN / "decision.profile.yaml",
    BUILTIN / "profile-conformance.tool.yaml",
    BUILTIN / "decision-evidence.tool.yaml",
]
_CORPUS_FILES = sorted(CORPUS.glob("*.yaml"))


def _full_registry() -> Registry:
    registry = Registry()
    for path in [*_BUILTIN_FILES, *_CORPUS_FILES]:
        registry.add(load_definition_file(path))
    return registry


def test_appendix_a_validates_end_to_end_with_the_full_corpus() -> None:
    registry = _full_registry()
    process = load_definition_file(APPENDIX_A)
    findings = validate_definition(process, registry)
    assert findings == [], "\n".join(
        f"{f.rule} [{f.node}]: {f.message}" for f in findings
    )


def test_every_corpus_and_builtin_file_is_itself_valid() -> None:
    """Each supporting definition validates on its own too, not just as an
    unexamined bystander to Appendix A's own success."""

    registry = _full_registry()
    for path in [*_BUILTIN_FILES, *_CORPUS_FILES]:
        definition = load_definition_file(path)
        findings = validate_definition(definition, registry)
        assert findings == [], f"{path.name}: " + "; ".join(
            f"{f.rule}: {f.message}" for f in findings
        )


@pytest.mark.parametrize(
    "missing_path", _CORPUS_FILES + _BUILTIN_FILES, ids=lambda p: p.name
)
def test_removing_any_referenced_definition_makes_v2_refuse_appendix_a(
    missing_path: Path,
) -> None:
    """Validates the whole set together, the way `sulis-workflows validate
    <files...>` does — some definitions are only referenced transitively (a
    checker's own `controls`, a Control's own `checker`), which only shows up
    when every file in the set is checked, not just the top-level Process."""

    registry = Registry()
    kept = []
    for path in [*_BUILTIN_FILES, *_CORPUS_FILES]:
        if path == missing_path:
            continue
        definition = load_definition_file(path)
        registry.add(definition)
        kept.append(definition)

    process = load_definition_file(APPENDIX_A)
    all_findings = [
        f for d in [process, *kept] for f in validate_definition(d, registry)
    ]
    assert any(f.rule == "V2" for f in all_findings), (
        f"removing {missing_path.name} should have made some reference unresolvable, but got: "
        + "; ".join(f"{f.rule}: {f.message}" for f in all_findings)
    )
