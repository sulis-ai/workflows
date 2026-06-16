"""Node factory — resolves NodeDef to Python callables for LangGraph.

Implements the NodeFactory Protocol and DefaultNodeFactory with 6 built-in
types: handler, function, gate, fan_out, routing, kind_invocation.

SEC-01: Allowlist enforcement for dotted-path imports.
ARC-02: Custom NodeFactory can be provided to GenericGraphCompiler.
WP-2: ``kind_invocation`` dispatches to KindHandler (stub resolution until
WP-KIND-HANDLER lands).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Protocol, runtime_checkable

from sulis_workflows.compiler.graph_dsl import NodeDef
from sulis_workflows.domain.actions.kind_invocation import KindInvocationAction
from sulis_workflows.domain.errors import CompilationError, NodeResolutionError

logger = logging.getLogger(__name__)


def _resolve_kind_handler() -> Any:
    """Return the KindHandler instance the dispatch callable will await.

    WP-2 ships a stub: KindHandler is created by WP-KIND-HANDLER. Until then
    the dispatch callable resolves the handler at invocation time via this
    helper, which raises a clear error if the handler is not yet wired. Tests
    patch this function to inject a fake handler.
    """
    raise NodeResolutionError(
        "KindHandler is not yet wired into the dispatch path. "
        "kind_invocation nodes cannot be executed until WP-KIND-HANDLER lands. "
        "Compilation succeeds (the graph shape is recognised); only invocation "
        "is blocked.",
        spec_ref="kind_invocation",
    )


class HandlerResolutionError(CompilationError):
    """Handler path is outside the allowed module prefix list."""

    error_code: str = "HANDLER_RESOLUTION_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, handler_path: str) -> None:
        self.handler_path = handler_path
        super().__init__(message)


@runtime_checkable
class NodeFactory(Protocol):
    """Protocol for node factories (ARC-02).

    Custom factories MAY additionally implement ``list_node_types() -> list[str]``
    to expose their node-type vocabulary to the compiler's introspection API
    (WP-2). The compiler treats this method as optional via duck-typing so the
    Protocol stays minimally-binding for existing factories.
    """

    def create(self, node_def: NodeDef, state_class: type) -> Any:
        """Create a callable from a node definition."""
        ...


class DefaultNodeFactory:
    """Default factory handling 6 built-in node types.

    Node types:
    - handler: Resolves via ActionRegistry + HandlerRegistry (production primary)
    - function: Direct callable or dotted-path import with allowlist
    - gate: Creates interrupt() node
    - fan_out: Pass-through (edges handle Send dispatch)
    - routing: Pass-through (edges handle conditional routing)
    - kind_invocation: Dispatches to KindHandler with a KindInvocationAction
      built from the node config (WP-2). Full handler wiring lands with
      WP-KIND-HANDLER; until then ``_resolve_kind_handler`` raises at
      invocation time.
    """

    # SEC-01: Only these module prefixes are allowed for dotted-path imports.
    ALLOWED_MODULE_PREFIXES: set[str] = {"sulis.services", "sulis.shared"}

    _REGISTERED_TYPES = frozenset(
        {"handler", "function", "gate", "fan_out", "routing", "kind_invocation"}
    )

    def list_node_types(self) -> list[str]:
        """Return the registered node-type vocabulary in deterministic order.

        Compiler introspection API (WP-2 DoD). Callers use this to validate
        graph definitions before compilation or to surface available types in
        tooling.
        """
        return sorted(self._REGISTERED_TYPES)

    def create(self, node_def: NodeDef, state_class: type) -> Any:
        """Resolve a NodeDef to a callable."""
        if node_def.type == "handler":
            return self._resolve_handler(node_def)
        elif node_def.type == "function":
            return self._resolve_function(node_def)
        elif node_def.type == "gate":
            return self._resolve_gate(node_def)
        elif node_def.type in ("fan_out", "routing"):
            return self._resolve_passthrough(node_def)
        elif node_def.type == "kind_invocation":
            return self._resolve_kind_invocation(node_def)
        else:
            raise NodeResolutionError(
                f"Unknown node type '{node_def.type}' for node '{node_def.id}'. "
                f"Registered types: {sorted(self._REGISTERED_TYPES)}",
                spec_ref=node_def.id,
            )

    def _resolve_handler(self, node_def: NodeDef) -> Any:
        """Resolve a handler node via ActionRegistry + HandlerRegistry."""
        if not node_def.action_type:
            raise CompilationError(
                f"Handler node '{node_def.id}' requires action_type but none provided"
            )

        # Import here to avoid circular imports — these are in shared/service_layer
        from sulis.shared.service_layer.action_registry import ActionRegistry
        from sulis.shared.service_layer.handler_registry import handler_registry

        action_cls = ActionRegistry.get_by_action_type(node_def.action_type)
        if action_cls is None:
            raise NodeResolutionError(
                f"Handler node '{node_def.id}': no Action registered for "
                f"action_type '{node_def.action_type}'",
                spec_ref=node_def.action_type,
            )

        state_to_input = node_def.state_to_input
        output_to_state = node_def.output_to_state
        node_id = node_def.id

        async def handler_node(state: dict) -> dict:
            input_kwargs = {
                input_field: state[state_field]
                for state_field, input_field in state_to_input.items()
                if state_field in state
            }
            # Get the input model class from the Action's generic parameter
            input_model_cls = action_cls.__orig_bases__[0].__args__[0]
            input_data = input_model_cls(**input_kwargs)
            action = action_cls(
                input_data=input_data,
                user_id=state.get("user_id", "system"),
            )
            handler = handler_registry.get_handler(type(action))
            result_action = await handler.execute(action)
            if result_action.error:
                raise RuntimeError(f"Handler node '{node_id}' failed: {result_action.error}")
            result = result_action.result
            state_update: dict[str, Any] = {}
            for result_attr, state_field in output_to_state.items():
                if hasattr(result, result_attr):
                    state_update[state_field] = getattr(result, result_attr)
                elif isinstance(result, dict) and result_attr in result:
                    state_update[state_field] = result[result_attr]
            return state_update

        handler_node.__name__ = f"handler_{node_id}"
        return handler_node

    def _resolve_function(self, node_def: NodeDef) -> Any:
        """Resolve a function node — direct callable or dotted-path import."""
        handler = node_def.handler

        if handler is None:
            raise NodeResolutionError(
                f"Function node '{node_def.id}' requires handler but none provided",
                spec_ref=node_def.id,
            )

        # Direct callable passthrough
        if callable(handler):
            return handler

        # Dotted-path string import with SEC-01 allowlist enforcement
        if isinstance(handler, str):
            if not self.ALLOWED_MODULE_PREFIXES:
                raise HandlerResolutionError(
                    f"Function node '{node_def.id}': empty allowlist rejects all paths",
                    handler_path=handler,
                )

            if not any(handler.startswith(prefix) for prefix in self.ALLOWED_MODULE_PREFIXES):
                raise HandlerResolutionError(
                    f"Function node '{node_def.id}': handler path '{handler}' "
                    f"not in allowed prefixes {sorted(self.ALLOWED_MODULE_PREFIXES)}",
                    handler_path=handler,
                )

            # Import the module and get the attribute
            parts = handler.rsplit(".", 1)
            if len(parts) != 2:
                raise NodeResolutionError(
                    f"Function node '{node_def.id}': invalid dotted path '{handler}'",
                    spec_ref=handler,
                )
            module_path, attr_name = parts
            try:
                module = importlib.import_module(module_path)
                return getattr(module, attr_name)
            except (ImportError, AttributeError) as e:
                raise CompilationError(
                    f"Function node '{node_def.id}': failed to import '{handler}': {e}"
                ) from e

        raise NodeResolutionError(
            f"Function node '{node_def.id}': handler must be callable or dotted-path string, "
            f"got {type(handler).__name__}",
            spec_ref=node_def.id,
        )

    def _resolve_gate(self, node_def: NodeDef) -> Any:
        """Create a gate node that calls interrupt()."""
        from sulis_workflows.compiler.nodes.gate_node import make_gate_node

        return make_gate_node(node_def.id)

    def _resolve_passthrough(self, node_def: NodeDef) -> Any:
        """Create a pass-through node for fan_out/routing."""
        node_id = node_def.id

        def passthrough(state: dict) -> dict:
            return {}

        passthrough.__name__ = f"passthrough_{node_id}"
        return passthrough

    def _resolve_kind_invocation(self, node_def: NodeDef) -> Any:
        """Compile a ``kind_invocation`` node into a KindHandler dispatch
        callable (WP-2).

        Validation happens here at compile time so a malformed graph fails
        fast rather than at execution. Required keys (``apiVersion``,
        ``kind``) live in ``node_def.config``; their absence raises a typed
        :class:`CompilationError`. Handler resolution is deferred to
        invocation time via :func:`_resolve_kind_handler` (the test seam) so
        WP-KIND-HANDLER can drop in the real handler without forcing a
        compile-time import dependency.
        """
        config = node_def.config or {}

        def _require(key: str) -> Any:
            value = config.get(key)
            if not value:
                raise CompilationError(
                    f"kind_invocation node '{node_def.id}': missing required config key '{key}'"
                )
            return value

        api_version = _require("apiVersion")
        kind = _require("kind")

        # Freeze the action shape at compile time. Refs are propagated for the
        # Kind compiler to resolve at invocation; metadata_* default to empty
        # string when omitted (the Kind compiler resolves them from the
        # ResourceKindRegistry per ADR-208).
        action = KindInvocationAction(
            api_version=str(api_version),
            kind=str(kind),
            metadata_name=str(config.get("metadata_name", "")),
            metadata_version=str(config.get("metadata_version", "")),
            content_brief_id=config.get("content_brief_id"),
            refs=dict(config.get("refs", {})),
        )

        node_id = node_def.id

        async def kind_invocation_dispatch(state: dict) -> dict:
            handler = _resolve_kind_handler()
            return await handler.handle(action)

        kind_invocation_dispatch.__name__ = f"kind_invocation_{node_id}"
        return kind_invocation_dispatch
