"""Generic gate node — interrupt() for human-in-the-loop approval.

OBS-03: Structured logging for gate interrupt and resume events.
REL-06: State preserved across interrupt/resume.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from langgraph.types import interrupt

logger = logging.getLogger(__name__)


def make_gate_node(node_id: str) -> Callable:
    """Create a generic gate node that triggers LangGraph interrupt().

    Args:
        node_id: Unique gate identifier for logging.

    Returns:
        A callable that pauses execution via interrupt() and returns
        the resume value as a state update.
    """

    def gate_fn(state: dict) -> dict:
        execution_id = state.get("execution_id", "unknown")

        gate_context = {
            "gate_id": node_id,
            "execution_id": execution_id,
            "awaiting": "approval",
        }

        logger.info(
            "Gate interrupt: gate_id=%s, execution_id=%s",
            node_id,
            execution_id,
            extra={
                "gate_id": node_id,
                "execution_id": execution_id,
                "event": "gate_interrupt",
            },
        )

        wait_start = time.monotonic()
        decision = interrupt(gate_context)
        wait_ms = (time.monotonic() - wait_start) * 1000

        logger.info(
            "Gate resume: gate_id=%s, execution_id=%s, wait_ms=%.2f",
            node_id,
            execution_id,
            wait_ms,
            extra={
                "gate_id": node_id,
                "execution_id": execution_id,
                "event": "gate_resume",
                "wait_ms": wait_ms,
            },
        )

        # Return the decision as a state update
        if isinstance(decision, dict):
            return decision
        return {"gate_decision": decision}

    gate_fn.__name__ = f"gate_{node_id}"
    return gate_fn
