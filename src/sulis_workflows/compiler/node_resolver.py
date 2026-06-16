"""Node resolver — maps DAG node type + spec_ref to Python callables.

Factory pattern: each node type maps to a factory function.
No eval/exec — only registered factories (SEC-DATA-01).
"""

from __future__ import annotations

from typing import Any

from sulis_workflows.compiler.dag_parser import DAGNode
from sulis_workflows.compiler.nodes.content_node import make_content_node
from sulis_workflows.compiler.nodes.gate import make_gate_node
from sulis_workflows.compiler.nodes.step import make_step_node
from sulis_workflows.compiler.ports.spec_repository import SpecRepository
from sulis_workflows.domain.errors import NodeResolutionError
from sulis_workflows.runtime.adapters import Adapters


class NodeResolver:
    """Resolves DAG nodes to Python callables for LangGraph.

    `adapters` is the runner-injected port bundle; nodes that need a port (e.g. a content
    node needs `LLMPort`) resolve it from here. Defaults to an empty bundle — a node that
    needs a port the runner didn't inject raises a clear `MissingAdapterError`, never a crash.
    """

    def __init__(self, spec_repo: SpecRepository, adapters: Adapters | None = None) -> None:
        self._spec_repo = spec_repo
        self._adapters = adapters or Adapters()

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
            # tool_dispatch + sandbox_root are resolved lazily inside the node (the
            # primitive is only known once the spec loads at execution time) — a step
            # that names a primitive but has no injected port raises a clear error then.
            return make_step_node(
                node.id,
                node.spec_ref,
                self._spec_repo,
                tool_dispatch=self._adapters.tool_dispatch,
                sandbox_root=self._adapters.sandbox_root,
            )
        elif node.type == "content":
            cfg = node.config or {}
            return make_content_node(
                node.id,
                str(cfg.get("input_key", "prompt")),
                str(cfg.get("output_key", "answer")),
                llm=self._adapters.require("llm"),  # the injected port (DR-040)
                model=str(cfg.get("model", "claude-sonnet-4-20250514")),
            )
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
