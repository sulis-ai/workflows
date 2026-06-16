"""Step node factory — the most common node type in OFM DAGs.

Creates closures that load step specs at execution time and produce
state updates for OFMGraphState.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sulis_workflows._tracing import span_context
from sulis_workflows.compiler.metrics import get_compiler_metrics
from sulis_workflows.compiler.ports.spec_repository import SpecRepository

logger = logging.getLogger(__name__)


def make_step_node(node_id: str, spec_ref: str, spec_repo: SpecRepository) -> Any:
    """Create a step node callable for LangGraph.

    Returns a function (state) -> dict that:
    1. Loads the step spec from the repository
    2. Returns state updates (completed_nodes + step_outputs)
    """

    def step_fn(state: dict) -> dict:
        metrics = get_compiler_metrics()

        with span_context(
            "compiler.node.step",
            attributes={"node_id": node_id, "spec_ref": spec_ref},
        ):
            start = time.monotonic()
            logger.info("Node execution start: %s", node_id)

            output: dict[str, Any] = {"spec_ref": spec_ref}
            if spec_ref:
                try:
                    spec = spec_repo.load_step_spec(spec_ref)
                    output["spec"] = spec
                except KeyError:
                    output["spec"] = None

            elapsed_ms = (time.monotonic() - start) * 1000
            metrics.record_node_execution_time(node_id, "step", elapsed_ms)
            logger.info("Node execution end: %s (%.1fms)", node_id, elapsed_ms)

            return {
                "completed_nodes": [node_id],
                "step_outputs": {node_id: output},
            }

    step_fn.__name__ = f"step_{node_id}"
    return step_fn
