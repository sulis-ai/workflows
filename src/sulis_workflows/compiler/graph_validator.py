"""Graph validator — topology and structural rule checking.

Validates graph topology against structural rules. Supports both
DAG (acyclic) and cyclic graphs — aligning with LangGraph's native
capabilities.

Cycles are permitted when they have a conditional exit path.
Unbounded cycles (no exit) are rejected.

Rules (original):
  GV-01: Unbounded cycle (cycle with no conditional exit edge)
  GV-02: Missing node reference in depends_on
  GV-03: No root node (all nodes have dependencies)
  GV-05: Gate has != 1 successor
  GV-08: Self-loop (node depends on itself)
  GV-11: Invalid node ID format

Rules (GRAPH.yaml — active when state declarations present):
  GV-NEW-01: reads/writes must reference declared state channels
  GV-NEW-02: Step nodes must declare execution type
  GV-NEW-03: Routing back-edges need max_iterations + exit_condition
  GV-NEW-04: Content nodes must have context blocks
  SEC-02: State types must be in allowlist
"""

from __future__ import annotations

import re

import networkx as nx

from sulis_workflows.compiler.dag_parser import ParsedDAG
from sulis_workflows.domain.errors import GraphValidationError

_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# Base OFMGraphState channels — always valid without explicit declaration
_BASE_STATE_CHANNELS = frozenset(
    {
        "execution_id",
        "outcome_id",
        "phase",
        "completed_nodes",
        "step_outputs",
        "gate_decisions",
        "metadata",
    }
)

# SEC-02: Allowed state types
_ALLOWED_STATE_TYPES = frozenset({"str", "int", "float", "bool", "dict", "list"})


class GraphValidator:
    """Validates graph topology and structural rules.

    Permits cycles when they contain a conditional exit path (routing
    or fan_out node), matching LangGraph's native cycle support.
    """

    def validate(self, dag: ParsedDAG) -> None:
        node_ids = {n.id for n in dag.nodes}
        successor_map = dag.get_successor_map()

        # Original rules (always run)
        self._check_gv11_id_format(dag)
        self._check_gv08_self_loops(dag)
        self._check_gv02_missing_refs(dag, node_ids)
        self._check_gv03_root_exists(dag)
        self._check_gv01_unbounded_cycles(dag, node_ids)
        self._check_gv05_gate_successors(dag, successor_map)
        self._check_for_each_fields(dag, node_ids)
        self._check_while_fields(dag, node_ids)

        # GRAPH.yaml rules — only active when state declarations present
        # (indicates GRAPH.yaml format, not legacy DAG.yaml)
        if dag.state:
            self._check_sec02_state_types(dag)
            self._check_gv_new_01_state_channels(dag)
            self._check_gv_new_02_execution_type(dag)
            self._check_gv_new_03_backedge_bounds(dag)
            self._check_gv_new_04_content_context(dag)

    def _check_gv01_unbounded_cycles(self, dag: ParsedDAG, node_ids: set[str]) -> None:
        """GV-01: Detect cycles with no conditional exit path.

        Cycles through routing or fan_out nodes are permitted because
        they have conditional edges that provide an exit path.
        Cycles through only step/gate nodes with simple edges are
        unbounded and rejected.
        """
        g = nx.DiGraph()
        for node in dag.nodes:
            g.add_node(node.id)
            for dep in node.depends_on:
                g.add_edge(dep, node.id)

        # Find all strongly connected components (cycles)
        node_type_map = {n.id: n.type for n in dag.nodes}

        for scc in nx.strongly_connected_components(g):
            if len(scc) < 2:
                continue  # Single node — not a cycle (self-loops caught by GV-08)

            # Check if any node in the cycle has a conditional exit capability.
            # routing, fan_out, and while nodes have conditional edges by definition.
            has_conditional_exit = any(
                node_type_map.get(node_id) in ("routing", "fan_out", "while") for node_id in scc
            )

            if not has_conditional_exit:
                cycle_path = " -> ".join(sorted(scc))
                raise GraphValidationError(
                    f"GV-01: Unbounded cycle detected: {cycle_path}. "
                    "Cycles must include a routing or fan_out node to provide "
                    "a conditional exit path.",
                    rule_id="GV-01",
                )

    def _check_gv02_missing_refs(self, dag: ParsedDAG, node_ids: set[str]) -> None:
        for node in dag.nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    raise GraphValidationError(
                        f"GV-02: Missing node reference '{dep}' in depends_on of node '{node.id}'",
                        rule_id="GV-02",
                        node_id=node.id,
                    )

    def _check_gv03_root_exists(self, dag: ParsedDAG) -> None:
        roots = [n for n in dag.nodes if not n.depends_on]
        if not roots:
            raise GraphValidationError(
                "GV-03: No root node found (all nodes have dependencies)",
                rule_id="GV-03",
            )

    def _check_gv05_gate_successors(
        self, dag: ParsedDAG, successor_map: dict[str, list[str]]
    ) -> None:
        for node in dag.nodes:
            if node.type == "gate":
                count = len(successor_map.get(node.id, []))
                if count == 0:
                    # Terminal gate (end of graph) — allowed
                    continue
                if count != 1:
                    raise GraphValidationError(
                        f"GV-05: Gate '{node.id}' has {count} successors (expected exactly 1)",
                        rule_id="GV-05",
                        node_id=node.id,
                    )

    def _check_gv08_self_loops(self, dag: ParsedDAG) -> None:
        for node in dag.nodes:
            if node.id in node.depends_on:
                raise GraphValidationError(
                    f"GV-08: Self-loop: '{node.id}' depends on itself",
                    rule_id="GV-08",
                    node_id=node.id,
                )

    def _check_gv11_id_format(self, dag: ParsedDAG) -> None:
        for node in dag.nodes:
            if not _VALID_ID_RE.match(node.id):
                raise GraphValidationError(
                    f"GV-11: Invalid node ID '{node.id}'",
                    rule_id="GV-11",
                    node_id=node.id,
                )

    # -- GRAPH.yaml rules (new) -----------------------------------------

    def _check_gv_new_01_state_channels(self, dag: ParsedDAG) -> None:
        """GV-NEW-01: reads/writes must reference declared state channels."""
        declared = {s.name for s in dag.state} | _BASE_STATE_CHANNELS
        for node in dag.nodes:
            if node.execution is None:
                continue  # Legacy node without execution field — skip
            for channel in node.reads:
                if channel not in declared:
                    raise GraphValidationError(
                        f"GV-NEW-01: Node '{node.id}' reads undeclared channel '{channel}'",
                        rule_id="GV-NEW-01",
                        node_id=node.id,
                    )
            for channel in node.writes:
                if channel not in declared:
                    raise GraphValidationError(
                        f"GV-NEW-01: Node '{node.id}' writes undeclared channel '{channel}'",
                        rule_id="GV-NEW-01",
                        node_id=node.id,
                    )

    def _check_gv_new_02_execution_type(self, dag: ParsedDAG) -> None:
        """GV-NEW-02: Step nodes must declare execution type."""
        for node in dag.nodes:
            if node.type == "step" and node.execution is None:
                raise GraphValidationError(
                    f"GV-NEW-02: Step node '{node.id}' missing execution type "
                    "(expected 'process', 'content', or 'planning')",
                    rule_id="GV-NEW-02",
                    node_id=node.id,
                )

    def _check_gv_new_03_backedge_bounds(self, dag: ParsedDAG) -> None:
        """GV-NEW-03: Routing back-edges need max_iterations."""
        for node in dag.nodes:
            if node.type != "routing":
                continue
            routes = (node.config or {}).get("routes", {})
            for target_id in routes.values():
                # Check if this route creates a back-edge (target is an ancestor)
                if self._is_ancestor(target_id, node.id, dag):
                    if node.max_iterations is None:
                        raise GraphValidationError(
                            f"GV-NEW-03: Routing node '{node.id}' creates back-edge "
                            f"to '{target_id}' without max_iterations",
                            rule_id="GV-NEW-03",
                            node_id=node.id,
                        )

    def _is_ancestor(self, candidate: str, node_id: str, dag: ParsedDAG) -> bool:
        """Check if candidate is an ancestor of node_id in the dependency graph."""
        visited: set[str] = set()
        stack = [node_id]
        node_map = {n.id: n for n in dag.nodes}
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            n = node_map.get(current)
            if n is None:
                continue
            for dep in n.depends_on:
                if dep == candidate:
                    return True
                stack.append(dep)
        return False

    def _check_gv_new_04_content_context(self, dag: ParsedDAG) -> None:
        """GV-NEW-04: Content nodes must have context blocks."""
        for node in dag.nodes:
            if node.execution == "content" and node.context is None:
                raise GraphValidationError(
                    f"GV-NEW-04: Content node '{node.id}' missing context block",
                    rule_id="GV-NEW-04",
                    node_id=node.id,
                )

    def _check_for_each_fields(self, dag: ParsedDAG, node_ids: set[str]) -> None:
        """GV-09: for_each nodes must have required fields."""
        for node in dag.nodes:
            if node.type != "for_each":
                continue
            cfg = node.config or {}
            for field in ("collection_field", "item_field", "graph_ref", "results_field"):
                if not cfg.get(field):
                    raise GraphValidationError(
                        f"GV-09: for_each node '{node.id}' missing required field '{field}'",
                        rule_id="GV-09",
                        node_id=node.id,
                    )
            if cfg.get("item_field") == "workspace_path":
                raise GraphValidationError(
                    f"GV-09: for_each node '{node.id}': item_field must not be 'workspace_path'",
                    rule_id="GV-09",
                    node_id=node.id,
                )

    def _check_while_fields(self, dag: ParsedDAG, node_ids: set[str]) -> None:
        """GV-10: while nodes must have required fields; body must reference a known node."""
        for node in dag.nodes:
            if node.type != "while":
                continue
            cfg = node.config or {}
            for field in ("condition_field", "body"):
                if not cfg.get(field):
                    raise GraphValidationError(
                        f"GV-10: while node '{node.id}' missing required field '{field}'",
                        rule_id="GV-10",
                        node_id=node.id,
                    )
            if cfg.get("max_iterations") is None:
                raise GraphValidationError(
                    f"GV-10: while node '{node.id}' missing required field 'max_iterations'",
                    rule_id="GV-10",
                    node_id=node.id,
                )
            body = cfg.get("body", "")
            if body and body not in node_ids:
                raise GraphValidationError(
                    f"GV-10: while node '{node.id}' body '{body}' references unknown node",
                    rule_id="GV-10",
                    node_id=node.id,
                )

    def _check_sec02_state_types(self, dag: ParsedDAG) -> None:
        """SEC-02: State types must be in allowlist."""
        for sd in dag.state:
            if sd.type not in _ALLOWED_STATE_TYPES:
                raise GraphValidationError(
                    f"SEC-02: State channel '{sd.name}' has disallowed type "
                    f"'{sd.type}'. Allowed: {sorted(_ALLOWED_STATE_TYPES)}",
                    rule_id="SEC-02",
                )


# Backwards compatibility alias
DAGValidator = GraphValidator
