"""`sulis-workflows validate` and `sulis-workflows explain` (WP-01 scope item 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_validate_exits_zero_for_a_clean_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A POLICY control has no checker and no other references to resolve — the
    # simplest genuinely self-contained document to prove a clean exit with.
    doc = tmp_path / "policy.yaml"
    doc.write_text(
        """
api_version: sulis.workflows/v1
kind: CONTROL
id: may-run
version: 1.0.0
type: POLICY
title: May this run
"""
    )
    code = main(["validate", str(doc)])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out


def test_validate_exits_non_zero_and_names_the_rule_on_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "tool.yaml"
    doc.write_text((FIXTURES / "refused" / "tool-unknown-field.yaml").read_text())
    code = main(["validate", str(doc)])
    err = capsys.readouterr().err
    assert code == 1
    assert "V1" in err


def test_validate_resolves_references_across_multiple_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / "finding.yaml"
    profile.write_text(
        """
api_version: sulis.workflows/v1
kind: PROFILE
id: finding
version: 1.0.0
title: Finding
grounded_in: "W3C PROV-O prov:wasDerivedFrom"
schema:
  type: object
  required: [id, claim, source]
  properties:
    id: { type: string }
    claim: { type: string, minLength: 10 }
    source: { type: string }
  additionalProperties: false
"""
    )
    tool = tmp_path / "tool.yaml"
    tool.write_text(
        """
api_version: sulis.workflows/v1
kind: TOOL
id: echo
version: 1.0.0
title: Echo
inputs: { value: { type: string } }
output: { value: { type: string } }
controls: [ { profile: finding@1 } ]
mechanism: { kind: CODE, ref: "pkg.mod:fn" }
effect: QUERY
"""
    )
    code = main(["validate", str(profile), str(tool)])
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "OK" in out


def test_explain_lists_nodes_loops_gates_and_endings(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["explain", str(FIXTURES / "accepted" / "process-appendix-a.yaml")])
    out = capsys.readouterr().out
    assert code == 0
    assert "nodes:" in out
    assert "sign-off: GATE" in out
    assert "gates:" in out
    assert "sign-off (APPROVAL):" in out
    assert "endings:" in out
    assert "COMPLETE (SUCCESS):" in out
    assert "ESCALATED (engine-added)" in out


def test_explain_shows_the_format_default_for_an_unset_loop_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WP-01 A4: a loop with no budget validates and `explain` shows the
    default from §15 (10), read from one constant, not repeated."""

    doc = tmp_path / "p.yaml"
    doc.write_text(
        """
api_version: sulis.workflows/v1
kind: PROCESS
id: p
version: 1.0.0
title: P
state:
  verdict: { type: "enum[SURVIVED, DROPPED]", reducer: REPLACE }
start: route
nodes:
  route:
    type: ROUTE
    when:
      - { if: 'state.verdict == "SURVIVED"', end: DONE }
      - { if: 'state.verdict == "DROPPED"', next: route, loop: {} }
endings:
  DONE: { outcome: SUCCESS, says: "Done." }
"""
    )
    code = main(["explain", str(doc)])
    out = capsys.readouterr().out
    assert code == 0
    assert f"budget={fmt_defaults.LOOP_BUDGET}" in out
    assert fmt_defaults.LOOP_BUDGET == 10
