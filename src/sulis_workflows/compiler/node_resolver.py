"""Node resolver — maps DAG node type + spec_ref to Python callables.

Factory pattern: each node type maps to a factory function.
No eval/exec — only registered factories (SEC-DATA-01).
"""

from __future__ import annotations

from typing import Any

from sulis_workflows.compiler.dag_parser import DAGNode
from sulis_workflows.compiler.nodes.gate import make_gate_node
from sulis_workflows.compiler.nodes.step import make_step_node
from sulis_workflows.compiler.ports.spec_repository import SpecRepository
from sulis_workflows.domain.errors import NodeResolutionError


class NodeResolver:
    """Resolves DAG nodes to Python callables for LangGraph."""

    def __init__(self, spec_repo: SpecRepository) -> None:
        self._spec_repo = spec_repo

    def resolve(self, node: DAGNode) -> Any:
        """Resolve a DAG node to a callable.

        Args:
            node: Parsed DAG node.

        Returns:
            A callable suitable for graph.add_node().

        Raises:
            NodeResolutionError: If the node type is unsupported.
        """
        if node.type == "step":
            return make_step_node(node.id, node.spec_ref, self._spec_repo)
        elif node.type == "gate":
            return make_gate_node(node.id)
        elif node.type in ("fan_out", "routing", "for_each", "while"):
            # These types are handled as edge functions or specialised handlers
            # in OutcomeGraphBuilder. Return a pass-through for the legacy path.
            return self._make_passthrough(node.id)
        else:
            raise NodeResolutionError(
                f"Unsupported node type '{node.type}' for node '{node.id}'",
                spec_ref=node.spec_ref or node.id,
            )

    def _make_passthrough(self, node_id: str) -> Any:
        def passthrough(state: dict) -> dict:
            return {"completed_nodes": [node_id]}

        passthrough.__name__ = f"passthrough_{node_id}"
        return passthrough
