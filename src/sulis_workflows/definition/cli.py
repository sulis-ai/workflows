"""`sulis-workflows validate <files...>` and `sulis-workflows explain <file>`
(WP-01 scope item 8). Registered as a console script (`pyproject.toml`).

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition import model
from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import Finding, validate_definition


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _fmt_for(path: str) -> str:
    return "json" if path.endswith(".json") else "yaml"


def _print_finding(path: str, finding: Finding) -> None:
    node_part = f" [{finding.node}]" if finding.node else ""
    print(f"{path}: {finding.rule}{node_part}: {finding.message}", file=sys.stderr)
    if finding.fix:
        print(f"{path}: {finding.rule}{node_part}: fix: {finding.fix}", file=sys.stderr)


def cmd_validate(paths: list[str]) -> int:
    """Loads every file first (so cross-file references resolve against the
    whole set), then validates each. Exits non-zero if any file has a finding."""

    registry = Registry()
    loaded: list[tuple[str, model.Definition]] = []
    findings_by_path: dict[str, list[Finding]] = {}

    for path in paths:
        try:
            definition = load_definition(_read(path), fmt=_fmt_for(path))
        except DefinitionError as exc:
            findings_by_path[path] = [
                Finding(rule=exc.rule, message=exc.message, node=exc.node, fix=exc.schema_path)
            ]
            continue
        registry.add(definition)
        loaded.append((path, definition))

    for path, definition in loaded:
        findings_by_path[path] = validate_definition(definition, registry)

    any_findings = False
    for path in paths:
        for finding in findings_by_path.get(path, []):
            any_findings = True
            _print_finding(path, finding)
        if path not in findings_by_path or not findings_by_path[path]:
            print(f"{path}: OK")

    return 1 if any_findings else 0


def _resolved_loop_budget(loop: model.LoopSpec, process: model.Process) -> int:
    if loop.budget is not None:
        return loop.budget
    if process.defaults and process.defaults.loop_budget is not None:
        return process.defaults.loop_budget
    return fmt_defaults.LOOP_BUDGET


def _iter_loops(process: model.Process):
    for node_id, node in process.nodes.items():
        if isinstance(node, model.RouteNode):
            for option in node.when:
                if option.loop:
                    yield node_id, option.loop
        elif isinstance(node, model.GateNode):
            for verdict, route in node.on.items():
                if route.loop:
                    yield f"{node_id}.on.{verdict}", route.loop
        elif isinstance(node, model.StepNode) and node.on_control_fail and node.on_control_fail.then and (
            node.on_control_fail.then.loop
        ):
            yield f"{node_id}.on_control_fail", node.on_control_fail.then.loop


def cmd_explain(path: str) -> int:
    try:
        definition = load_definition(_read(path), fmt=_fmt_for(path))
    except DefinitionError as exc:
        print(f"{path}: {exc.rule}: {exc.message}", file=sys.stderr)
        return 1

    print(f"{definition.header.kind} {definition.header.id}@{definition.header.version} — {definition.header.title}")

    if not isinstance(definition, model.Process):
        print("(explain only describes PROCESS documents in detail)")
        return 0

    print("\nnodes:")
    for node_id, node in definition.nodes.items():
        print(f"  {node_id}: {node.type}")

    loops = list(_iter_loops(definition))
    print("\nloops:" if loops else "\nloops: (none)")
    for where, loop in loops:
        print(f"  {where}: budget={_resolved_loop_budget(loop, definition)}")

    gates = [(nid, n) for nid, n in definition.nodes.items() if isinstance(n, model.GateNode)]
    print("\ngates:" if gates else "\ngates: (none)")
    for node_id, gate in gates:
        deciders = ", ".join(d.ref or d.permission or d.role or "?" for d in gate.deciders) or "(a person, by default)"
        print(f"  {node_id} ({gate.kind}): {gate.asks!r} — deciders: {deciders}")

    print("\nendings:")
    for name, ending in definition.endings.items():
        print(f"  {name} ({ending.outcome}): {ending.says!r}")
    for name in fmt_defaults.ENGINE_ENDINGS:
        print(f"  {name} (engine-added)")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sulis-workflows")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate one or more definition files")
    validate_parser.add_argument("files", nargs="+")

    explain_parser = subparsers.add_parser("explain", help="explain a single PROCESS definition file")
    explain_parser.add_argument("file")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return cmd_validate(args.files)
    if args.command == "explain":
        return cmd_explain(args.file)
    raise AssertionError(f"unreachable: unknown command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
