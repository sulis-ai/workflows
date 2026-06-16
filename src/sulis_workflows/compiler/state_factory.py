"""State factory — builds dynamic TypedDict classes from StateSchema.

Transforms a StateSchema (list of StateFieldDef) into a TypedDict class
that LangGraph's StateGraph accepts as the state type. Supports reducers
via typing.Annotated for parallel-safe fan-out merges.

SEC-02: Type whitelist enforcement — only safe types allowed.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any

from sulis_workflows.compiler.graph_dsl import StateSchema
from sulis_workflows.domain.errors import CompilationError

# SEC-02: Only these base types are allowed in state schemas.
_ALLOWED_TYPES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
}

# Reducer name → reducer function
_REDUCERS: dict[str, Any] = {
    "merge_dicts": operator.or_,
    "append": operator.add,
}


class SchemaValidationError(CompilationError):
    """State schema contains a disallowed type."""

    error_code: str = "SCHEMA_VALIDATION_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, type_name: str) -> None:
        self.type_name = type_name
        super().__init__(message)


def _resolve_type(type_hint: str) -> type:
    """Resolve a type hint string to a Python type.

    Supports:
    - Simple types: "str", "int", "float", "bool", "dict", "list"
    - Parameterised: "list[str]", "dict[str, str]"
    - Optional: "Optional[str]" → str | None

    Raises SchemaValidationError for disallowed types.
    """
    hint = type_hint.strip()

    # Handle Optional[T]
    if hint.startswith("Optional[") and hint.endswith("]"):
        inner = hint[9:-1]
        inner_type = _resolve_type(inner)
        return inner_type | None  # type: ignore[return-value]

    # Handle parameterised types like list[str], dict[str, str]
    if "[" in hint:
        base_name = hint[: hint.index("[")]
        if base_name not in _ALLOWED_TYPES:
            raise SchemaValidationError(
                f"Disallowed type '{base_name}' in state schema",
                type_name=base_name,
            )
        # For LangGraph state, we just use the base type — the annotation
        # is informational. LangGraph doesn't enforce parameterised types.
        inner_str = hint[hint.index("[") + 1 : -1]
        # Validate inner types recursively
        for part in _split_type_args(inner_str):
            part = part.strip()
            if part:
                _resolve_type(part)
        return _ALLOWED_TYPES[base_name]

    # Simple type
    if hint not in _ALLOWED_TYPES:
        raise SchemaValidationError(
            f"Disallowed type '{hint}' in state schema",
            type_name=hint,
        )
    return _ALLOWED_TYPES[hint]


def _split_type_args(s: str) -> list[str]:
    """Split comma-separated type args, respecting nested brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch == "[":
            depth += 1
            current.append(ch)
        elif ch == "]":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def build_state_class(name: str, schema: StateSchema) -> type:
    """Build a TypedDict class from a StateSchema.

    Args:
        name: Name for the generated TypedDict class.
        schema: State field definitions with optional reducers.

    Returns:
        A TypedDict class suitable for LangGraph StateGraph.
    """
    annotations: dict[str, Any] = {}

    for field_def in schema.fields:
        resolved_type = _resolve_type(field_def.type_hint)

        if field_def.reducer and field_def.reducer in _REDUCERS:
            # Apply reducer via Annotated for LangGraph parallel safety
            annotations[field_def.name] = Annotated[resolved_type, _REDUCERS[field_def.reducer]]
        else:
            annotations[field_def.name] = resolved_type

    # Create TypedDict dynamically
    state_class = type(name, (dict,), {"__annotations__": annotations})
    return state_class
