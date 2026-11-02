"""D49's documents: the spec, the changelog, the 0.13.0 pins, the run record, and that
the library carries a step's `session` and never acts on it."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[2]
SPEC = ROOT / "docs/spec/process-definition.md"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_spec_records_session() -> None:
    spec = SPEC.read_text(encoding="utf-8")
    start = spec.index("### 7.1 Step")
    section_7_1 = spec[start : spec.index("### 7.2", start)]
    for words in (
        "`session`",
        "session: { mode: FRESH, agent: { different_from: build }, model_role: JUDGEMENT, sees: [test-runs] }",
        "a role, never a model id",
        "A step without `session` gets the host's default",
        "every step must pass when run fresh",
    ):
        assert words in section_7_1, words
    assert re.search(
        r"^\| V20 session \| `agent\.different_from` naming no node, a node that is not "
        r"a STEP, or the step itself \(D49\) \|$",
        spec,
        re.MULTILINE,
    )
    assert (
        "| Step session object (mode, agent, model role, sees) | this format (D49); "
        "values agreed with sulis-ai/platform ADR-290 | OWN |" in spec
    )
    d48 = spec.index("**D48 ")
    after_d48 = [
        m.group(0) for m in re.finditer(r"^\*\*D\d+", spec[d48:], re.MULTILINE)
    ]
    assert after_d48[:2] == ["**D48", "**D49"]
    d49 = spec[spec.index("**D49 ") :].split("\n", 1)[0]
    for part in ("*Context:*", "*Options considered:*", "*Outcome:*"):
        assert part in d49, part
    for part in ("*Consequences:*", "*Reversal:*"):
        assert part in d49, part


def test_changelog_has_empty_unreleased_above_0_13_0() -> None:
    # "Empty" is true only until the next change adds its entry, so this holds what stays
    # true: Unreleased sits directly above the release and kept none of its entries.
    changelog = _read("CHANGELOG.md")
    heads = re.findall(r"^## \[.*$", changelog, re.MULTILINE)
    assert heads[:2] == ["## [Unreleased]", "## [0.13.0] \u2014 2026-11-02"]
    unreleased = changelog[changelog.index(heads[0]) : changelog.index(heads[1])]
    release = changelog[changelog.index(heads[1]) : changelog.index(heads[2])]
    added = release[release.index("### Added") : release.index("### Fixed")]
    for decision in ("D46", "D47", "D48", "D49"):
        assert re.search(rf"^- \*\*{decision}\b", added, re.MULTILINE), decision
        assert not re.search(rf"^- \*\*{decision}\b", unreleased, re.MULTILINE), (
            decision
        )


def test_install_guides_and_pyproject_say_0_13_0() -> None:
    assert re.search(r'^version = "0\.13\.0"$', _read("pyproject.toml"), re.MULTILINE)
    for guide in ("docs/adopting.md", "docs/getting-started.md"):
        text = _read(guide)
        assert "workflows.git@v0.13.0" in text
        assert "0.12.2" not in text


def test_engine_and_compiler_never_read_session() -> None:
    for folder in ("compiler", "engine"):
        for source in (ROOT / "src/sulis_workflows" / folder).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            assert "StepSession" not in text, source
            assert not re.search(r"\.session\b", text), source


def test_run_record_for_d49_validates() -> None:
    runs = ROOT / "docs/runs"
    schema = json.loads((runs / "agent-run.schema.json").read_text(encoding="utf-8"))
    records = []
    for path in runs.glob("*.agent-run.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        headlines = [d["headline"] for d in record.get("decisions", [])]
        if any(headline.startswith("D49") for headline in headlines):
            records.append((path, record))
    assert len(records) == 1
    path, record = records[0]
    assert path.name == f"{record['id']}.agent-run.json"
    assert list(Draft202012Validator(schema).iter_errors(record)) == []
