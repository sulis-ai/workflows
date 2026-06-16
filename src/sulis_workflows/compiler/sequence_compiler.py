"""SequenceGraphCompiler — Level 2: SEQUENCE.md to chained subgraphs.

Chains multiple outcome subgraphs (compiled via OutcomeGraphCompiler)
into a single LangGraph StateGraph using .add_node() with compiled
subgraphs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sulis_workflows.compiler.outcome_compiler import OutcomeGraphCompiler
from sulis_workflows.compiler.ports.spec_repository import SpecRepository
from sulis_workflows.compiler.state import OFMGraphState

logger = logging.getLogger(__name__)


class SequenceGraphCompiler:
    """Compiles a sequence definition into a chained StateGraph."""

    def __init__(
        self,
        spec_repo: SpecRepository,
        outcome_compiler: OutcomeGraphCompiler,
    ) -> None:
        self._spec_repo = spec_repo
        self._outcome_compiler = outcome_compiler

    def compile(self, sequence_id: str, *, checkpointer: Any | None = None) -> CompiledStateGraph:
        start = time.monotonic()
        logger.info("Compiling sequence: %s", sequence_id)

        seq_spec = self._spec_repo.load_sequence(sequence_id)
        outcomes = seq_spec["outcomes"]

        graph = StateGraph(OFMGraphState)

        prev_id: str | None = None
        for entry in outcomes:
            outcome_id = entry["id"]
            # Compile the outcome subgraph (without checkpointer — parent owns it)
            subgraph = self._outcome_compiler.compile(outcome_id)
            graph.add_node(outcome_id, subgraph)

            if prev_id is None:
                graph.set_entry_point(outcome_id)
            else:
                graph.add_edge(prev_id, outcome_id)

            prev_id = outcome_id

        # Last outcome connects to END
        if prev_id:
            graph.add_edge(prev_id, END)

        compiled = graph.compile(checkpointer=checkpointer)

        elapsed = (time.monotonic() - start) * 1000
        logger.info(
            "Compiled sequence: %s in %.1fms (%d outcomes)",
            sequence_id,
            elapsed,
            len(outcomes),
        )

        return compiled
