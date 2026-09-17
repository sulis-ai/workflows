"""Errors the definition package raises. No sulis.* import, no vendor SDK."""

from __future__ import annotations


class DefinitionError(Exception):
    """A definition document was refused.

    Fail closed (CLAUDE.md): every refusal names the rule that refused it, the schema
    or document path involved, and — once known — the node. ``str(error)`` reads as a
    single human message; the structured fields are what a validator finding is built
    from (spec §14: ``{ rule, node, message, fix }``).
    """

    def __init__(
        self,
        message: str,
        *,
        rule: str,
        schema_path: str | None = None,
        node: str | None = None,
        fix: str | None = None,
    ) -> None:
        self.message = message
        self.rule = rule
        self.schema_path = schema_path
        self.node = node
        self.fix = fix
        parts = [f"[{rule}]", message]
        if schema_path:
            parts.append(f"(schema: {schema_path})")
        if node:
            parts.append(f"(node: {node})")
        super().__init__(" ".join(parts))
