"""Prompt utility scaffolding — Layer 1 building blocks (per ADR-216).

These four utility functions (``build_system_prompt``, ``format_node_input``,
``normalize_response``, ``parse_json_response``) are generic prompt-construction
and response-parsing helpers consumable from any Layer 3 flow — they are not
bound to the ``production_plan`` sub-package they originated in.

Per ADR-216, this is the canonical Layer 1 location for the utility scaffold.
A deprecation shim at the legacy path
``sulis_workflows.domain.sequences.production_plan.prompts`` re-exports
these symbols for backwards compatibility; new code MUST import from here.

Layer 1 framing (per the slice-2 TDD §8 and Layer 1 SPEC):

- LLM transports (``BaseChatModel`` subclasses) live at
  ``sulis_workflows.infrastructure.llm/`` — that placement is settled
  post-MIG-2 (see ADR-216 Path A) and is NOT re-located by this WP.
- Prompt utility scaffolding (this module) lives at
  ``sulis_workflows.domain.prompts``.

If a future WP introduces prompt template files (``.txt`` / ``.md`` / ``.yaml``)
the canonical location is this same directory; the utility module and the
templates would be siblings.
"""

from __future__ import annotations

import json
from typing import Any


def build_system_prompt(
    *,
    role: str,
    task_description: str,
    standards: list[str] | None = None,
    output_format: str = "json",
    response_schema: str | None = None,
) -> str:
    """Build a system prompt for a content node.

    Args:
        role: The analytical role (e.g., "Decomposition Analyst").
        task_description: What the node should accomplish.
        standards: Standards from the GRAPH.yaml context block.
        output_format: Expected output format ("json" or "yaml").
        response_schema: Example of expected JSON structure.
    """
    parts = [
        f"You are a {role} working on a production plan.",
        "",
        f"## Task\n{task_description}",
    ]

    if standards:
        parts.append("")
        parts.append("## Standards to Apply")
        for s in standards:
            parts.append(f"- {s}")

    parts.append("")
    parts.append(
        f"## Output Format\nRespond with valid {output_format.upper()} only. No commentary."
    )

    if response_schema:
        parts.append("")
        parts.append(f"## Response Schema\n{response_schema}")

    return "\n".join(parts)


def format_node_input(fields: dict[str, Any]) -> str:
    """Format state fields as structured user content for an LLM call.

    Args:
        fields: Dict of field_name → value from state.
    """
    sections: list[str] = []
    for name, value in fields.items():
        if isinstance(value, (dict, list)):
            formatted = json.dumps(value, indent=2, default=str)
        else:
            formatted = str(value)
        sections.append(f"## {name}\n{formatted}")

    return "\n\n".join(sections)


def normalize_response(parsed: Any, *, expect: str) -> Any:
    """Normalize LLM response to expected type.

    LLMs sometimes wrap lists in dicts or return unexpected structures.
    This provides a defense-in-depth layer after parse_json_response().

    Args:
        parsed: The parsed JSON value.
        expect: Expected top-level type — "list", "dict", or "str".
    """
    if expect == "list" and isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                return v
        return []
    if expect == "dict" and isinstance(parsed, list):
        return {"items": parsed}
    return parsed


def parse_json_response(response: str) -> Any:
    """Parse a JSON response from an LLM, handling markdown fences.

    Strips ```json ... ``` fencing if present.
    """
    text = response.strip()
    if text.startswith("```"):
        # Remove opening fence
        first_newline = text.index("\n")
        text = text[first_newline + 1 :]
        # Remove closing fence
        if text.endswith("```"):
            text = text[:-3].rstrip()

    return json.loads(text)


__all__ = [
    "build_system_prompt",
    "format_node_input",
    "normalize_response",
    "parse_json_response",
]
