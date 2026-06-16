"""Gate node — interrupt() + Command(resume=...) for human-in-the-loop.

The highest-risk component: uses LangGraph's interrupt() to persist
state and pause execution, then resumes via Command(resume=...).
"""

from __future__ import annotations

import logging
import time

from langgraph.types import interrupt

from sulis_workflows._tracing import span_context
from sulis_workflows.compiler.metrics import get_compiler_metrics

logger = logging.getLogger(__name__)


def make_gate_node(node_id: str):
    """Create a gate node callable for LangGraph.

    Returns a function that:
    1. Calls interrupt() to pause execution and persist state
    2. On resume, records the decision in gate_decisions
    """

    def gate_fn(state: dict) -> dict:
        metrics = get_compiler_metrics()
        execution_id = state.get("execution_id", "")

        with span_context(
            "compiler.node.gate",
            attributes={"gate_id": node_id, "execution_id": execution_id},
        ):
            gate_context = {
                "gate_id": node_id,
                "execution_id": execution_id,
                "completed_nodes": state.get("completed_nodes", []),
                "awaiting": "human_approval",
            }

            logger.info("Gate interrupt: gate_id=%s, execution_id=%s", node_id, execution_id)
            wait_start = time.monotonic()
            decision = interrupt(gate_context)
            wait_ms = (time.monotonic() - wait_start) * 1000
            metrics.record_gate_wait_time(node_id, wait_ms)

            logger.info(
                "Gate resume: gate_id=%s, execution_id=%s, decision=%s",
                node_id,
                execution_id,
                decision.get("decision", "unknown"),
            )

            return {
                "gate_decisions": {node_id: decision["decision"]},
                "completed_nodes": [node_id],
            }

    gate_fn.__name__ = f"gate_{node_id}"
    return gate_fn
