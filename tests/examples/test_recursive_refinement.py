"""examples/recursive-refinement/: a v1 translation of sulis-ai/platform's
recursive-refinement controller (ADR-0020) validates end-to-end, the same
discipline test_appendix_a.py holds the spec's own worked example to —
including reusing the real, already-registered grounded-inquiry@1.0.0
process (tests/definition/fixtures/appendix_a_corpus/) rather than
restating it, so that corpus is part of this one's own registry too.

The classes below also drive it through the REAL engine (next()/report()),
not only validate() — the first version of this file validated only, and
that alone missed a real bug: `mechanism.inputs: { brief: brief }`, spec
§9.1's own literal worked-example syntax (bare, unqualified names), never
actually resolves against this engine's `_resolve_call_inputs`, which
reads `mechanism.inputs` straight off the CALLING process's own
`inputs.*`/`state.*`/`host.*`/`steps.*` namespaces — a bare name matches
none of them and silently resolves to `None`. `run-grounded-inquiry.tool.
yaml`/`recurse-into-node.tool.yaml` now use fully-qualified paths instead
(the same convention `tests/engine/test_run.py`'s own PROCESS-mechanism
tests already use); this file's own engine-execution tests are the
regression coverage that keeps that fix honest."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from sulis_workflows.definition.load import load_definition_file
from sulis_workflows.definition.model import Process
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import validate_definition
from sulis_workflows.domain.ports.claims import StubClaimsAdapter
from sulis_workflows.domain.ports.code_tool import StubCodeToolAdapter
from sulis_workflows.domain.ports.external_tool import StubExternalToolAdapter
from sulis_workflows.domain.ports.policy import StubPolicyAdapter
from sulis_workflows.domain.ports.records import StubRecordsAdapter
from sulis_workflows.engine.run import AnswerKind, EngineContext, next_, report

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


def _load_process() -> Process:
    process = load_definition_file(
        RECURSIVE_REFINEMENT / "recursive-refinement.process.yaml"
    )
    assert isinstance(process, Process)
    return process


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


# --------------------------------------------------------------- engine execution --

_PASS_RESULT: dict[str, Any] = {
    "result": {"control": "refinement-output-present@1", "passed": True, "findings": []}
}
_APPENDIX_A_PASS_RESULT: dict[str, Any] = {
    "result": {"control": "output-present@1", "passed": True, "findings": []}
}
_CODE_RESPONSES: dict[str, dict[str, Any]] = {
    "recursive_refinement.checkers:output_present": _PASS_RESULT,
    "recursive_refinement.tools:check_completeness": {
        "completeness_report": {"passed": True, "findings": []}
    },
    "recursive_refinement.tools:frame_brief": {
        "brief": {"question": "Should we build a new billing subsystem?"}
    },
    "appendix_a_corpus.checkers:output_present": _APPENDIX_A_PASS_RESULT,
    "appendix_a_corpus.tools:frame_question": {
        "framed_question": "Should we build a new billing subsystem?"
    },
    "appendix_a_corpus.tools:classify_inquiry": {"path": "SINGLE"},
}


def _fresh_ctx(registry: Registry) -> EngineContext:
    return EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=StubCodeToolAdapter(responses=_CODE_RESPONSES),
        external_tool=StubExternalToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="user:iain",
        platform_id="tenant-1",
    )


def _run(coro):
    return asyncio.run(coro)


def test_a_clear_node_mints_a_work_package_end_to_end() -> None:
    """The engine, not just the validator: classify -> route -> mint,
    driven through next()/report() to a real ENDED answer."""

    registry = _full_registry()
    process = _load_process()
    ctx = _fresh_ctx(registry)
    run_id = "run-clear-1"

    answer = _run(
        next_(
            process,
            run_id,
            "root",
            ctx,
            inputs={"node_brief": "Fix the login button color"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP and answer.node_id == "classify"

    answer = _run(
        report(
            process,
            run_id,
            "root",
            "classify",
            ctx,
            inputs={},
            host_inputs={},
            output={"cynefin_domain": "CLEAR"},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP and answer.node_id == "mint-work-package"

    answer = _run(
        report(
            process,
            run_id,
            "root",
            "mint-work-package",
            ctx,
            inputs={},
            host_inputs={},
            output={
                "work_package": {
                    "id": "wp-1",
                    "title": "Fix the login button color",
                    "executing_process": "conformance-convergence@1.0.0",
                }
            },
        )
    )
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "WORK_TREE_COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_a_complicated_node_recurses_through_for_each_over_two_wbs_children() -> None:
    """WP-03 Part 2 (D47): FOR_EACH is now engine-executed — the documented
    limit this test used to prove (a clean refusal at the fan-out) no
    longer holds, replaced by driving the real thing: the run reaches
    classify and wbs-decompose, then genuinely recurses into TWO wbs
    children (one at a time, `refine-each-child` declares no
    `max_concurrency`, default 1, spec §15), each child's own recursive
    call itself reaching a CLEAR leaf and minting a work package, before
    `completeness-gate` and `route-completeness` carry the run the rest of
    the way to `WORK_TREE_COMPLETE`."""

    registry = _full_registry()
    process = _load_process()
    ctx = _fresh_ctx(registry)
    run_id = "run-complicated-1"

    answer = _run(
        next_(
            process,
            run_id,
            "root",
            ctx,
            inputs={"node_brief": "Build a new billing subsystem"},
            host_inputs={},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP and answer.node_id == "classify"

    answer = _run(
        report(
            process,
            run_id,
            "root",
            "classify",
            ctx,
            inputs={},
            host_inputs={},
            output={"cynefin_domain": "COMPLICATED"},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP and answer.node_id == "wbs-decompose"

    answer = _run(
        report(
            process,
            run_id,
            "root",
            "wbs-decompose",
            ctx,
            inputs={},
            host_inputs={},
            output={
                "wbs_children": [
                    {"id": "c1", "brief": "Design the billing schema"},
                    {"id": "c2", "brief": "Build the billing API"},
                ]
            },
        )
    )
    # Item 0's own recursive call reaches CLEAR -> classify -> mint, in a
    # NESTED scope bubbled up untouched (§9.3, the same rule a PARALLEL
    # branch's own hand-off already followed, D46, one level further in).
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "classify"
    item0_recursion_scope = answer.scope
    assert item0_recursion_scope is not None
    assert "refine-each-child.item[0]" in item0_recursion_scope

    answer = _run(
        report(
            process,
            run_id,
            item0_recursion_scope,
            "classify",
            ctx,
            inputs={},
            host_inputs={},
            output={"cynefin_domain": "CLEAR"},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "mint-work-package"
    assert answer.scope == item0_recursion_scope

    answer = _run(
        report(
            process,
            run_id,
            item0_recursion_scope,
            "mint-work-package",
            ctx,
            inputs={},
            host_inputs={},
            output={
                "work_package": {
                    "id": "wp-c1",
                    "title": "Design the billing schema",
                    "executing_process": "conformance-convergence@1.0.0",
                }
            },
        )
    )
    # Item 0 is now ENDED -- max_concurrency's own default (1) only opens
    # item 1 once item 0 is done, never both at once.
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "classify"
    item1_recursion_scope = answer.scope
    assert item1_recursion_scope is not None
    assert "refine-each-child.item[1]" in item1_recursion_scope
    assert item1_recursion_scope != item0_recursion_scope

    answer = _run(
        report(
            process,
            run_id,
            item1_recursion_scope,
            "classify",
            ctx,
            inputs={},
            host_inputs={},
            output={"cynefin_domain": "CLEAR"},
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "mint-work-package"

    answer = _run(
        report(
            process,
            run_id,
            item1_recursion_scope,
            "mint-work-package",
            ctx,
            inputs={},
            host_inputs={},
            output={
                "work_package": {
                    "id": "wp-c2",
                    "title": "Build the billing API",
                    "executing_process": "conformance-convergence@1.0.0",
                }
            },
        )
    )
    # Both items ENDED -> refine-each-child's own ALL_COMPLETE policy is
    # satisfied -> completeness-gate (a CODE tool, dispatched inline, the
    # stub registry's own _CODE_RESPONSES already answers `passed: True`)
    # -> route-completeness -> WORK_TREE_COMPLETE.
    assert answer.kind is AnswerKind.ENDED
    assert answer.ending == "WORK_TREE_COMPLETE"
    assert answer.outcome == "SUCCESS"


def test_a_complex_node_dispatches_the_real_grounded_inquiry_process_and_resumes_its_hand_off() -> (
    None
):
    """Proves spec §9's own composition claim for real: the COMPLEX path's
    process call genuinely descends into grounded-inquiry's own separately
    governed scope (not a stub, the real registered process), and a
    hand-off from inside that nested scope bubbles up and can be resumed
    (twice, through two of grounded-inquiry's own steps) exactly as spec
    §9.3 describes — "every answer names the scope ... at any depth"."""

    registry = _full_registry()
    process = _load_process()
    ctx = _fresh_ctx(registry)
    run_id = "run-complex-1"
    node_brief = {"node_brief": "Should we build a new billing subsystem?"}

    answer = _run(
        next_(process, run_id, "root", ctx, inputs=node_brief, host_inputs={})
    )
    assert answer.kind is AnswerKind.TOOL_STEP and answer.node_id == "classify"

    answer = _run(
        report(
            process,
            run_id,
            "root",
            "classify",
            ctx,
            inputs=node_brief,
            host_inputs={},
            output={"cynefin_domain": "COMPLEX"},
        )
    )
    # The hand-off now comes from INSIDE grounded-inquiry's own nested
    # scope (spec §9.3's own "at any depth") — not a `TOOL_STEP` for this
    # process's own `dispatch-grounded-inquiry` node.
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "gather"
    nested_scope = answer.scope
    assert nested_scope == "root/dispatch-grounded-inquiry"

    answer = _run(
        report(
            process,
            run_id,
            nested_scope,
            "gather",
            ctx,
            inputs=node_brief,
            host_inputs={},
            output={
                "findings": [
                    {
                        "id": "f1",
                        "claim": "Cancellation surveys cite pricing changes.",
                        "source": "survey-1",
                    }
                ]
            },
        )
    )
    assert answer.kind is AnswerKind.TOOL_STEP
    assert answer.node_id == "interrogate"
    assert answer.scope == nested_scope
