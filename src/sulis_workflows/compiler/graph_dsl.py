"""Graph DSL data model — domain-agnostic graph definitions.

Frozen dataclasses representing a declarative graph definition that can be
compiled to a LangGraph StateGraph by GenericGraphCompiler.

Node types: handler, function, gate, fan_out, routing, kind_invocation,
for_each, while.
Three edge forms: simple (str), conditional (dict), fan-out (list).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StateFieldDef:
    """A single field in a graph state schema."""

    name: str
    type_hint: str = "str"
    reducer: str | None = None
    default: Any = None


@dataclass(frozen=True)
class StateSchema:
    """Container for state field definitions."""

    fields: list[StateFieldDef] = field(default_factory=list)


@dataclass(frozen=True)
class NodeDef:
    """A node in a graph definition.

    Attributes:
        id: Unique node identifier within the graph.
        type: One of "handler", "function", "gate", "fan_out", "routing",
            "kind_invocation".
        handler: For "function" type — callable or dotted import path.
        action_type: For "handler" type — ActionRegistry key (e.g. "manifest.compute_diff").
        state_to_input: For "handler" type — maps state fields to Action input fields.
        output_to_state: For "handler" type — maps Action result attrs to state fields.
        config: Type-specific config (e.g. route_key/routes for routing).
    """

    id: str
    type: str
    handler: str | Callable | None = None
    action_type: str | None = None
    state_to_input: dict[str, str] = field(default_factory=dict)
    output_to_state: dict[str, str] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeDef:
    """An edge connecting two nodes.

    Three forms:
    - Simple: source → target (str)
    - Conditional: source → {"field": route_key, "routes": {value: target}} (dict)
    - Fan-out: source → [target_1, target_2, ...] (list)
    """

    source: str
    target: str | list[str] | dict[str, Any] = ""
    condition: str | None = None


@dataclass(frozen=True)
class GraphDefinition:
    """Top-level DSL container for a graph definition.

    Attributes:
        name: Human-readable graph name.
        nodes: List of node definitions.
        edges: List of edge definitions.
        state_schema: State field definitions with optional reducers.
        entry_point: Explicit entry node (auto-detected from roots if omitted).
        terminal_nodes: Explicit terminal nodes (auto-detected from leaves if omitted).
    """

    name: str
    nodes: list[NodeDef] = field(default_factory=list)
    edges: list[EdgeDef] = field(default_factory=list)
    state_schema: StateSchema = field(default_factory=StateSchema)
    entry_point: str | None = None
    terminal_nodes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> GraphDefinition:
        """Parse a dict into a GraphDefinition.

        Expected dict schema (from USER_GUIDE.md Section 2.2):
        - name: str
        - nodes: list of {id, type, handler?, action_type?, state_to_input?, output_to_state?, config?}
        - edges: list of {from, to, condition?}
        - state_schema: {fields: {name: {type, reducer?, default?}}}
        - entry_point?: str
        - terminal_nodes?: list[str]
        """
        # Parse state schema
        raw_schema = d.get("state_schema", {})
        raw_fields = raw_schema.get("fields", {})
        state_fields: list[StateFieldDef] = []

        if isinstance(raw_fields, dict):
            for fname, fdef in raw_fields.items():
                if isinstance(fdef, dict):
                    state_fields.append(
                        StateFieldDef(
                            name=fname,
                            type_hint=fdef.get("type", "str"),
                            reducer=fdef.get("reducer"),
                            default=fdef.get("default"),
                        )
                    )
                else:
                    state_fields.append(StateFieldDef(name=fname, type_hint=str(fdef)))
        elif isinstance(raw_fields, list):
            for fdef in raw_fields:
                state_fields.append(
                    StateFieldDef(
                        name=fdef["name"],
                        type_hint=fdef.get("type", fdef.get("type_hint", "str")),
                        reducer=fdef.get("reducer"),
                        default=fdef.get("default"),
                    )
                )

        schema = StateSchema(fields=state_fields)

        # Parse nodes
        nodes: list[NodeDef] = []
        for raw_node in d.get("nodes", []):
            nodes.append(
                NodeDef(
                    id=raw_node["id"],
                    type=raw_node["type"],
                    handler=raw_node.get("handler"),
                    action_type=raw_node.get("action_type"),
                    state_to_input=raw_node.get("state_to_input", {}),
                    output_to_state=raw_node.get("output_to_state", {}),
                    config=raw_node.get("config", {}),
                )
            )

        # Parse edges — translate "from"/"to" keys to source/target
        edges: list[EdgeDef] = []
        for raw_edge in d.get("edges", []):
            source = raw_edge.get("from", raw_edge.get("source", ""))
            target = raw_edge.get("to", raw_edge.get("target", ""))
            condition = raw_edge.get("condition")
            edges.append(EdgeDef(source=source, target=target, condition=condition))

        return cls(
            name=d.get("name", "unnamed"),
            nodes=nodes,
            edges=edges,
            state_schema=schema,
            entry_point=d.get("entry_point"),
            terminal_nodes=d.get("terminal_nodes", []),
        )
