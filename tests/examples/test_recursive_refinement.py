"""examples/recursive-refinement/: a v1 translation of sulis-ai/platform's
recursive-refinement controller (ADR-0020) validates end-to-end, the same
discipline test_appendix_a.py holds the spec's own worked example to —
including reusing the real, already-registered grounded-inquiry@1.0.0
process (tests/definition/fixtures/appendix_a_corpus/) rather than
restating it, so that corpus is part of this one's own registry too."""

from __future__ import annotations

from pathlib import Path

import pytest

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import validate_definition

BUILTIN = (
    Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition" / "builtin"
)
APPENDIX_A_CORPUS = (
    Path(__file__).parents[1] / "definition" / "fixtures" / "appendix_a_corpus"
)
APPENDIX_A = (
    Path(__file__).parents[1]
    / "definition"
    / "fixtures"
    / "accepted"
    / "process-appendix-a.yaml"
)
RECURSIVE_REFINEMENT = Path(__file__).parents[2] / "examples" / "recursive-refinement"

_BUILTIN_FILES = sorted(BUILTIN.glob("*.yaml"))
_APPENDIX_A_FILES = [*sorted(APPENDIX_A_CORPUS.glob("*.yaml")), APPENDIX_A]
_RR_FILES = sorted(RECURSIVE_REFINEMENT.glob("*.yaml"))
_ALL_FILES = [*_BUILTIN_FILES, *_APPENDIX_A_FILES, *_RR_FILES]


def _full_registry() -> Registry:
    registry = Registry()
    for path in _ALL_FILES:
        registry.add(load_definition_file(path))
    return registry


def test_recursive_refinement_validates_end_to_end_with_the_full_corpus() -> None:
    registry = _full_registry()
    process = load_definition_file(
        RECURSIVE_REFINEMENT / "recursive-refinement.process.yaml"
    )
    findings = validate_definition(process, registry)
    assert findings == [], "\n".join(
        f"{f.rule} [{f.node}]: {f.message}" for f in findings
    )


def test_every_supporting_definition_is_itself_valid() -> None:
    """Each supporting definition validates on its own too, not just as an
    unexamined bystander to the process's own success."""

    registry = _full_registry()
    for path in _ALL_FILES:
        definition = load_definition_file(path)
        findings = validate_definition(definition, registry)
        assert findings == [], f"{path.name}: " + "; ".join(
            f"{f.rule}: {f.message}" for f in findings
        )


@pytest.mark.parametrize("missing_path", _RR_FILES, ids=lambda p: p.name)
def test_removing_any_recursive_refinement_file_makes_v2_refuse_the_process(
    missing_path: Path,
) -> None:
    """Validates the whole set together, the way `sulis-workflows validate
    <files...>` does — some definitions are only referenced transitively (a
    checker's own `controls`), which only shows up when every file in the
    set is checked, not just the top-level Process. Every file this
    translation itself owns is load-bearing: removing any one of them
    breaks the set (the shared appendix_a_corpus/builtin dependencies are
    not re-checked here — that is test_appendix_a.py's own job)."""

    registry = Registry()
    kept = []
    for path in _ALL_FILES:
        if path == missing_path:
            continue
        definition = load_definition_file(path)
        registry.add(definition)
        kept.append(definition)

    process = load_definition_file(
        RECURSIVE_REFINEMENT / "recursive-refinement.process.yaml"
    )
    all_findings = list(validate_definition(process, registry))
    for definition in kept:
        all_findings.extend(validate_definition(definition, registry))

    assert any(f.rule == "V2" for f in all_findings), (
        f"removing {missing_path.name} did not produce any V2 finding — "
        "it may be an unreferenced, dead file"
    )
