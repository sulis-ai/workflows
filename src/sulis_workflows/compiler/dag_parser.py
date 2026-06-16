"""DAG/GRAPH parser — YAML dict to typed ParsedDAG model.

Handles two root key schemas:
  - ``dag:``   — legacy DAG.yaml format
  - ``graph:`` — GRAPH.yaml format with state declarations, execution types,
                 reads/writes contracts, and context blocks

Validates schema structure and node types. Does NOT validate
graph topology (that is GraphValidator's responsibility).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sulis_workflows.domain.errors import DAGValidationError

VALID_NODE_TYPES = frozenset(
    {"step", "content", "gate", "fan_out", "routing", "route_decider", "file_writer", "for_each", "while"}
)


@dataclass(frozen=True)
class StateDeclaration:
    """A declared state channel in a GRAPH.yaml."""

    name: str
    type: str  # "str" | "int" | "float" | "bool" | "dict" | "list"
    reducer: str | None = None
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class DAGNode:
    """A single node in a parsed DAG/GRAPH."""

    id: str
    type: str
    spec_ref: str = ""
    depends_on: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    # GRAPH.yaml fields (all optional for backward compat):
    execution: str | None = None  # "process" | "content" | "planning"
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    context: dict | None = None  # {input: [], processing: [], output: []}
    criticality: str = "standard"  # "critical" | "standard" | "trivial"
    max_iterations: int | None = None  # Required for planning nodes
    retry: dict | None = None  # {max_attempts, strategy}


@dataclass(frozen=True)
class ParsedDAG:
    """Typed representation of a parsed DAG.yaml or GRAPH.yaml."""

    nodes: list[DAGNode]
    state: list[StateDeclaration] = field(default_factory=list)

    def get_node(self, node_id: str) -> DAGNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def get_successor_map(self) -> dict[str, list[str]]:
        successors: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        for node in self.nodes:
            for dep in node.depends_on:
                if dep in successors:
                    successors[dep].append(node.id)
        return successors


class DAGParser:
    """Parses raw DAG/GRAPH YAML dict into a typed ParsedDAG model.

    Dual-path detection (CF-01):
      - ``graph:`` root key → GRAPH.yaml schema
      - ``dag:`` root key → legacy DAG.yaml schema
      - neither → DAGValidationError
    """

    def parse(self, dag_spec: dict) -> ParsedDAG:
        if "graph" in dag_spec:
            return self._parse_graph(dag_spec["graph"])
        if "dag" in dag_spec:
            return self._parse_dag(dag_spec["dag"])
        raise DAGValidationError(
            "Schema error: missing 'graph' or 'dag' root key",
            rule_id="SCHEMA",
        )

    # -- GRAPH.yaml path ------------------------------------------------

    def _parse_graph(self, graph: dict) -> ParsedDAG:
        """Parse GRAPH.yaml schema with state, execution, context."""
        raw_nodes = graph.get("nodes", [])
        if not raw_nodes:
            raise DAGValidationError("Schema error: empty nodes list", rule_id="SCHEMA")

        state = self._parse_state_declarations(graph.get("state", []))
        nodes = self._parse_nodes(raw_nodes)
        return ParsedDAG(nodes=nodes, state=state)

    def _parse_state_declarations(
        self,
        raw_state: list[dict],
    ) -> list[StateDeclaration]:
        return [
            StateDeclaration(
                name=s["name"],
                type=s.get("type", "str"),
                reducer=s.get("reducer"),
                default=s.get("default"),
                description=s.get("description", ""),
            )
            for s in raw_state
        ]

    # -- Legacy DAG.yaml path ------------------------------------------

    def _parse_dag(self, dag: dict) -> ParsedDAG:
        """Parse legacy DAG.yaml schema (existing behaviour, unchanged)."""
        if "nodes" not in dag:
            raise DAGValidationError("Schema error: missing 'nodes' key in dag", rule_id="SCHEMA")

        raw_nodes = dag["nodes"]
        if not raw_nodes:
            raise DAGValidationError("Schema error: empty nodes list", rule_id="SCHEMA")

        nodes = self._parse_nodes(raw_nodes)
        return ParsedDAG(nodes=nodes)

    # -- Shared node parsing -------------------------------------------

    def _parse_nodes(self, raw_nodes: list[dict]) -> list[DAGNode]:
        seen_ids: set[str] = set()
        nodes: list[DAGNode] = []

        for i, raw in enumerate(raw_nodes):
            if "id" not in raw:
                raise DAGValidationError(
                    f"Schema error: missing 'id' on node at index {i}",
                    rule_id="SCHEMA",
                    node_id=None,
                )
            if "type" not in raw:
                raise DAGValidationError(
                    f"Schema error: missing 'type' on node '{raw.get('id', i)}'",
                    rule_id="SCHEMA",
                    node_id=raw.get("id"),
                )

            node_id = raw["id"]
            node_type = raw["type"]

            if node_type not in VALID_NODE_TYPES:
                raise DAGValidationError(
                    f"Schema error: unknown type '{node_type}' on node '{node_id}'",
                    rule_id="SCHEMA",
                    node_id=node_id,
                )

            if node_id in seen_ids:
                raise DAGValidationError(
                    f"Schema error: duplicate id '{node_id}'",
                    rule_id="SCHEMA",
                    node_id=node_id,
                )
            seen_ids.add(node_id)

            # Pack for_each / while top-level fields into config so the builder
            # can read them without knowing the raw YAML layout.
            base_config = dict(raw.get("config", {}))
            if node_type == "for_each":
                for key in (
                    "collection_field",
                    "item_field",
                    "graph_ref",
                    "results_field",
                    "reducer",
                ):
                    if key in raw:
                        base_config.setdefault(key, raw[key])
                base_config.setdefault("reducer", "append")
            elif node_type == "while":
                for key in ("condition_field", "condition_value", "body", "max_iterations"):
                    if key in raw:
                        base_config.setdefault(key, raw[key])

            nodes.append(
                DAGNode(
                    id=node_id,
                    type=node_type,
                    spec_ref=raw.get("spec_ref", ""),
                    depends_on=raw.get("depends_on", []),
                    config=base_config,
                    execution=raw.get("execution"),
                    reads=raw.get("reads", []),
                    writes=raw.get("writes", []),
                    context=raw.get("context"),
                    criticality=raw.get("criticality", "standard"),
                    max_iterations=raw.get("max_iterations"),
                    retry=raw.get("retry"),
                )
            )

        return nodes
