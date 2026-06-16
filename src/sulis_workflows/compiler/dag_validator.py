"""DAG validator — topology and structural rule checking.

Validates ParsedDAG against rules DAG-01 through DAG-11.
Uses networkx for cycle detection.
"""

from __future__ import annotations

import re

import networkx as nx

from sulis_workflows.compiler.dag_parser import ParsedDAG
from sulis_workflows.domain.errors import DAGValidationError

_VALID_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class DAGValidator:
    """Validates ParsedDAG topology and structural rules."""

    def validate(self, dag: ParsedDAG) -> None:
        node_ids = {n.id for n in dag.nodes}
        successor_map = dag.get_successor_map()

        self._check_dag11_id_format(dag)
        self._check_dag08_self_loops(dag)
        self._check_dag02_missing_refs(dag, node_ids)
        self._check_dag03_root_exists(dag)
        self._check_dag01_cycles(dag)
        self._check_dag05_gate_successors(dag, successor_map)

    def _check_dag01_cycles(self, dag: ParsedDAG) -> None:
        g = nx.DiGraph()
        for node in dag.nodes:
            g.add_node(node.id)
            for dep in node.depends_on:
                g.add_edge(dep, node.id)
        try:
            cycle = nx.find_cycle(g, orientation="original")
            path = " -> ".join(e[0] for e in cycle)
            raise DAGValidationError(
                f"DAG-01: Cycle detected: {path}",
                rule_id="DAG-01",
            )
        except nx.NetworkXNoCycle:
            pass

    def _check_dag02_missing_refs(self, dag: ParsedDAG, node_ids: set[str]) -> None:
        for node in dag.nodes:
            for dep in node.depends_on:
                if dep not in node_ids:
                    raise DAGValidationError(
                        f"DAG-02: Missing node reference '{dep}' in depends_on of node '{node.id}'",
                        rule_id="DAG-02",
                        node_id=node.id,
                    )

    def _check_dag03_root_exists(self, dag: ParsedDAG) -> None:
        roots = [n for n in dag.nodes if not n.depends_on]
        if not roots:
            raise DAGValidationError(
                "DAG-03: No root node found (all nodes have dependencies)",
                rule_id="DAG-03",
            )

    def _check_dag05_gate_successors(
        self, dag: ParsedDAG, successor_map: dict[str, list[str]]
    ) -> None:
        for node in dag.nodes:
            if node.type == "gate":
                count = len(successor_map.get(node.id, []))
                if count != 1:
                    raise DAGValidationError(
                        f"DAG-05: Gate '{node.id}' has {count} successors (expected exactly 1)",
                        rule_id="DAG-05",
                        node_id=node.id,
                    )

    def _check_dag08_self_loops(self, dag: ParsedDAG) -> None:
        for node in dag.nodes:
            if node.id in node.depends_on:
                raise DAGValidationError(
                    f"DAG-08: Self-loop: '{node.id}' depends on itself",
                    rule_id="DAG-08",
                    node_id=node.id,
                )

    def _check_dag11_id_format(self, dag: ParsedDAG) -> None:
        for node in dag.nodes:
            if not _VALID_ID_RE.match(node.id):
                raise DAGValidationError(
                    f"DAG-11: Invalid node ID '{node.id}'",
                    rule_id="DAG-11",
                    node_id=node.id,
                )
