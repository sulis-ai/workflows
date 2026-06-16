"""Generic graph compiler — GraphDefinition to LangGraph CompiledStateGraph.

Domain-agnostic compiler that accepts a GraphDefinition (or dict) and
produces a LangGraph CompiledStateGraph. Does not import any domain-specific
types (OFM, tasks, etc.).

Orchestrates: normalise → validate → build state → add nodes → wire edges → compile.
Deterministic: same definition always produces the same graph.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from sulis_workflows.compiler.graph_dsl import (
    EdgeDef,
    GraphDefinition,
)
from sulis_workflows.compiler.node_factory import DefaultNodeFactory, NodeFactory
from sulis_workflows.compiler.state_factory import build_state_class
from sulis_workflows.domain.errors import CompilationError, GraphValidationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompilerMetrics:
    """OBS-01: Programmatic compilation metrics."""

    compilation_duration_ms: float
    node_count: int
    edge_count: int
    graph_name: str


class GenericGraphCompiler:
    """Compiles a GraphDefinition into a LangGraph CompiledStateGraph."""

    # SEC-03: Graph definition size limits to prevent resource exhaustion.
    MAX_NODES = 200
    MAX_EDGES = 500
    MAX_STATE_FIELDS = 100

    def __init__(self, node_factory: NodeFactory | None = None) -> None:
        self._node_factory = node_factory or DefaultNodeFactory()
        self._last_metrics: CompilerMetrics | None = None

    @property
    def last_metrics(self) -> CompilerMetrics | None:
        """OBS-01: Access metrics from the most recent compilation."""
        return self._last_metrics

    def list_node_types(self) -> list[str]:
        """Return the node-type vocabulary the configured factory recognises.

        Compiler introspection API (WP-2). Delegates to the node factory so
        custom factories (ARC-02) can declare their own vocabulary. Falls
        back to an empty list if a factory pre-dates the WP-2 contract and
        does not implement ``list_node_types``.
        """
        list_fn = getattr(self._node_factory, "list_node_types", None)
        if list_fn is None:
            return []
        return list(list_fn())

    def compile(
        self,
        definition: GraphDefinition | dict,
        *,
        checkpointer: Any | None = None,
    ) -> CompiledStateGraph:
        """Compile a graph definition to a LangGraph CompiledStateGraph.

        Args:
            definition: A GraphDefinition or dict (parsed via from_dict).
            checkpointer: Optional LangGraph checkpointer for gate resume.

        Returns:
            A compiled LangGraph StateGraph ready for ainvoke().

        Raises:
            CompilationError: On any compilation failure.
            DAGValidationError: On topology violations.
        """
        start = time.monotonic()

        try:
            # 1. Normalise input
            if isinstance(definition, dict):
                definition = GraphDefinition.from_dict(definition)

            graph_name = definition.name

            # SEC-03: Enforce size limits
            self._check_size_limits(definition)

            # 2. Build dynamic state class
            state_class = build_state_class(f"{graph_name}_state", definition.state_schema)

            # 3. Validate topology
            self._validate_topology(definition)

            # 4. Build StateGraph
            graph: StateGraph = StateGraph(state_class)

            # 5. Add nodes
            for node_def in definition.nodes:
                node_fn = self._node_factory.create(node_def, state_class)
                graph.add_node(node_def.id, node_fn)

            # 6. Wire edges
            self._wire_edges(graph, definition)

            # 7. Set entry point
            entry = definition.entry_point
            if entry:
                graph.set_entry_point(entry)
            else:
                roots = self._find_roots(definition)
                if len(roots) == 1:
                    graph.set_entry_point(roots[0])
                elif roots:
                    for root in roots:
                        graph.add_edge(START, root)
                else:
                    raise CompilationError(
                        f"Graph '{graph_name}': no entry point and no root nodes found"
                    )

            # 8. Wire terminal nodes to END
            terminals = definition.terminal_nodes
            if not terminals:
                terminals = self._find_leaves(definition)
            for terminal in terminals:
                # Only add terminal edge if not already wired by edges
                if not self._has_outgoing_edge(definition, terminal):
                    graph.add_edge(terminal, END)

            # 9. Compile
            compiled = graph.compile(checkpointer=checkpointer)

            elapsed_ms = (time.monotonic() - start) * 1000
            self._last_metrics = CompilerMetrics(
                compilation_duration_ms=elapsed_ms,
                node_count=len(definition.nodes),
                edge_count=len(definition.edges),
                graph_name=graph_name,
            )
            logger.info(
                "Compiled graph '%s' in %.1fms (%d nodes, %d edges)",
                graph_name,
                elapsed_ms,
                len(definition.nodes),
                len(definition.edges),
            )

            return compiled

        except (CompilationError, GraphValidationError):
            raise
        except Exception as e:
            definition_hash = self._hash_definition(definition)
            logger.error(
                "Compilation failed for graph (hash=%s): %s",
                definition_hash,
                e,
            )
            raise CompilationError(f"Compilation failed: {e}") from e

    def _check_size_limits(self, definition: GraphDefinition) -> None:
        """SEC-03: Enforce graph definition size limits."""
        if len(definition.nodes) > self.MAX_NODES:
            raise CompilationError(
                f"Graph '{definition.name}' has {len(definition.nodes)} nodes "
                f"(max {self.MAX_NODES})"
            )
        if len(definition.edges) > self.MAX_EDGES:
            raise CompilationError(
                f"Graph '{definition.name}' has {len(definition.edges)} edges "
                f"(max {self.MAX_EDGES})"
            )
        if len(definition.state_schema.fields) > self.MAX_STATE_FIELDS:
            raise CompilationError(
                f"Graph '{definition.name}' has {len(definition.state_schema.fields)} "
                f"state fields (max {self.MAX_STATE_FIELDS})"
            )

    def _validate_topology(self, definition: GraphDefinition) -> None:
        """Validate graph topology — check for self-loops and missing refs.

        Cycles are permitted (LangGraph supports them natively).
        Unbounded cycles are caught by GraphValidator on ParsedDAG paths.
        """
        node_ids = {n.id for n in definition.nodes}

        # Check for self-loops
        for edge in definition.edges:
            if isinstance(edge.target, str) and edge.source == edge.target:
                raise GraphValidationError(
                    f"GV-08: Self-loop: edge from '{edge.source}' to itself",
                    rule_id="GV-08",
                    node_id=edge.source,
                )

        # Check for missing node references in edges
        for edge in definition.edges:
            if edge.source not in node_ids:
                raise CompilationError(f"Edge references unknown source node '{edge.source}'")
            targets = self._extract_targets(edge)
            for target in targets:
                if target == END:
                    continue  # END is a LangGraph sentinel, not a graph node
                if target not in node_ids:
                    raise CompilationError(f"Edge references unknown target node '{target}'")

    def _extract_targets(self, edge: EdgeDef) -> list[str]:
        """Extract all target node IDs from an edge definition."""
        if isinstance(edge.target, str):
            return [edge.target] if edge.target else []
        elif isinstance(edge.target, list):
            return edge.target
        elif isinstance(edge.target, dict):
            routes = edge.target.get("routes", {})
            return list(routes.values())
        return []

    def _wire_edges(self, graph: StateGraph, definition: GraphDefinition) -> None:
        """Wire all edges into the StateGraph."""
        for edge in definition.edges:
            if isinstance(edge.target, str):
                # Simple edge
                graph.add_edge(edge.source, edge.target)
            elif isinstance(edge.target, list):
                # Fan-out edge — Send() to all targets
                targets = edge.target

                def make_fanout(t: list[str]):
                    def fanout_router(state: dict) -> list[Send]:
                        return [Send(target, state) for target in t]

                    return fanout_router

                graph.add_conditional_edges(edge.source, make_fanout(targets))
            elif isinstance(edge.target, dict):
                # Conditional routing edge
                route_field = edge.target.get("field", "route")
                routes = edge.target.get("routes", {})
                default_route = edge.target.get("default")

                def make_router(src: str, rf: str, rt: dict, dr: str | None):
                    _key_pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in rt) + r")\b")

                    def routing_fn(state: dict) -> str:
                        value = str(state.get(rf, "")).strip()
                        if value in rt:
                            return str(rt[value])
                        # LLM may prepend/append explanation — scan for a valid key
                        match = _key_pattern.search(value)
                        if match:
                            key = match.group(1)
                            logger.warning(
                                "routing.extracted_key node=%s field=%s key=%s",
                                src,
                                rf,
                                key,
                            )
                            return str(rt[key])
                        if dr is not None:
                            logger.warning(
                                "routing.fallback node=%s field=%s value=%r default=%s",
                                src,
                                rf,
                                value[:80],
                                dr,
                            )
                            return str(dr)
                        raise RuntimeError(
                            f"Routing node '{src}': no route for "
                            f"value '{value}' in field '{rf}'. "
                            f"Available routes: {list(rt.keys())}"
                        )

                    return routing_fn

                graph.add_conditional_edges(
                    edge.source, make_router(edge.source, route_field, routes, default_route)
                )

    def _find_roots(self, definition: GraphDefinition) -> list[str]:
        """Find nodes that are never targets of any edge."""
        all_targets: set[str] = set()
        for edge in definition.edges:
            all_targets.update(self._extract_targets(edge))
        return [n.id for n in definition.nodes if n.id not in all_targets]

    def _find_leaves(self, definition: GraphDefinition) -> list[str]:
        """Find nodes that are never sources of any edge."""
        all_sources = {e.source for e in definition.edges}
        return [n.id for n in definition.nodes if n.id not in all_sources]

    def _has_outgoing_edge(self, definition: GraphDefinition, node_id: str) -> bool:
        """Check if a node has any outgoing edge."""
        return any(e.source == node_id for e in definition.edges)

    def _hash_definition(self, definition: Any) -> str:
        """SHA-256 hash of definition repr for error logging (OBS-04)."""
        return hashlib.sha256(repr(definition).encode()).hexdigest()[:12]
