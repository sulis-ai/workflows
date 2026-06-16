"""IntentGraphCompiler — Level 3: natural language to compiled graph.

Single LLM inference pass: intent → DAG spec → validated → compiled.
Uses OutcomeGraphCompiler.compile_from_spec() for the final compilation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.domain.errors import CompilationError

logger = logging.getLogger(__name__)

DAG_GENERATION_PROMPT = """\
You are a DAG compiler. Given a natural language intent, produce a valid DAG \
specification as JSON.

The DAG must follow this schema:
- Top-level key: the intent slug (lowercase, hyphens)
- Contains "dag" object with "nodes" array
- Each node has: "id" (string), "type" ("step"|"gate"|"fan_out"|"routing"), \
"spec_ref" (string, format: "intent/node-id")
- Optional: "depends_on" (array of node IDs)
- Nodes execute in topological order based on depends_on
- First node(s) have no depends_on

Respond with ONLY valid JSON, no markdown fences or explanation.

Intent: {intent}
"""


@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM inference. Thin protocol over any chat model."""

    async def ainvoke(self, prompt: str) -> str:
        """Send a prompt and return the text response."""
        ...


class IntentGraphCompiler:
    """Compiles natural language intent to a StateGraph.

    Single LLM inference pass: intent → DAG spec → validated → compiled.
    """

    def __init__(
        self,
        llm: LLMPort,
        outcome_compiler: OutcomeGraphCompiler,
    ) -> None:
        self._llm = llm
        self._outcome_compiler = outcome_compiler

    async def compile(self, intent: str, *, checkpointer: Any | None = None) -> CompiledStateGraph:
        """Compile a natural language intent to an executable graph."""
        logger.info("Compiling intent: %s", intent[:100])

        # 1. LLM generates a DAG specification from intent
        dag_spec = await self._generate_dag_spec(intent)

        # 2. Compile using the outcome compiler (validates internally)
        return self._outcome_compiler.compile_from_spec(dag_spec, checkpointer=checkpointer)

    async def _generate_dag_spec(self, intent: str) -> dict:
        """Use LLM to generate a DAG spec from natural language."""
        prompt = DAG_GENERATION_PROMPT.format(intent=intent)
        response = await self._llm.ainvoke(prompt)

        try:
            spec = json.loads(response)
        except json.JSONDecodeError as e:
            raise CompilationError(f"LLM produced invalid JSON for intent: {e}") from e

        if not isinstance(spec, dict) or not spec:
            raise CompilationError("LLM produced empty or non-dict spec")

        # If spec has a "dag" key directly, return as-is
        if "dag" in spec:
            return spec

        # Otherwise unwrap: {"intent-slug": {"dag": {...}}} → {"dag": {...}}
        first_value = next(iter(spec.values()))
        if isinstance(first_value, dict) and "dag" in first_value:
            return first_value

        raise CompilationError("LLM produced spec without 'dag' key at any level")
