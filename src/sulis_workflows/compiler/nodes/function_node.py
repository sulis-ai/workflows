"""Generic function node — wraps a callable with execution instrumentation.

OBS-02: Structured logging with node_id, node_type, duration_ms, status.
REL-08: Exception handling — catches, logs, and re-raises.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


def make_function_node(handler: Callable, node_id: str) -> Callable:
    """Wrap a callable in execution instrumentation.

    Args:
        handler: The callable to execute (receives state dict, returns state update dict).
        node_id: Unique identifier for structured logging.

    Returns:
        An instrumented async callable suitable for LangGraph add_node().
    """

    async def function_node(state: dict) -> dict:
        start = time.monotonic()
        try:
            result = handler(state)
            # Support both sync and async handlers
            if hasattr(result, "__await__"):
                result = await result
            duration_ms = (time.monotonic() - start) * 1000
            logger.info(
                "Node execution: node_id=%s, node_type=function, duration_ms=%.2f, status=success",
                node_id,
                duration_ms,
                extra={
                    "node_id": node_id,
                    "node_type": "function",
                    "duration_ms": duration_ms,
                    "status": "success",
                },
            )
            return result if isinstance(result, dict) else {}
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            logger.exception(
                "Node execution: node_id=%s, node_type=function, duration_ms=%.2f, status=failure",
                node_id,
                duration_ms,
                extra={
                    "node_id": node_id,
                    "node_type": "function",
                    "duration_ms": duration_ms,
                    "status": "failure",
                },
            )
            raise

    function_node.__name__ = f"function_{node_id}"
    return function_node
