"""Prometheus metrics for the Graph Compiler.

IVS §6: Observability Requirements (OBS-MET-*)

Metrics:
- OBS-MET-01: compiler_compilation_time_ms - Compilation duration histogram
- OBS-MET-02: compiler_node_execution_time_ms - Node execution duration histogram
- OBS-MET-03: compiler_gate_wait_time_ms - Gate wait duration histogram
- OBS-MET-04: compiler_executions_total - Execution count by status
"""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

# OBS-MET-01: Compilation time histogram
# Labels: outcome_id
COMPILER_COMPILATION_TIME_MS = Histogram(
    "compiler_compilation_time_ms",
    "Time taken to compile DAG.yaml to StateGraph (milliseconds)",
    labelnames=["outcome_id"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
)

# OBS-MET-02: Node execution time histogram
# Labels: node_id, node_type
COMPILER_NODE_EXECUTION_TIME_MS = Histogram(
    "compiler_node_execution_time_ms",
    "Time taken to execute a single node (milliseconds)",
    labelnames=["node_id", "node_type"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000],
)

# OBS-MET-03: Gate wait time histogram
# Labels: gate_id
COMPILER_GATE_WAIT_TIME_MS = Histogram(
    "compiler_gate_wait_time_ms",
    "Time a gate waited for human approval (milliseconds)",
    labelnames=["gate_id"],
    buckets=[1000, 5000, 10000, 30000, 60000, 300000, 600000, 3600000],
)

# OBS-MET-04: Executions total counter
# Labels: status (completed, failed, awaiting_approval)
COMPILER_EXECUTIONS_TOTAL = Counter(
    "compiler_executions_total",
    "Total number of compiler executions by terminal status",
    labelnames=["status"],
)

# OBS-MET-05: Checkpoint save/load duration histogram
# Labels: operation (save, load, delete)
CHECKPOINT_SAVE_DURATION_MS = Histogram(
    "checkpoint_save_duration_ms",
    "Checkpoint save/load/delete duration in milliseconds",
    labelnames=["operation"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
)

# OBS-MET-05b: Checkpoint operations counter
# Labels: operation (save, load, delete), status (success, error)
CHECKPOINT_OPERATIONS_TOTAL = Counter(
    "checkpoint_operations_total",
    "Total checkpoint operations",
    labelnames=["operation", "status"],
)


class CompilerMetrics:
    """Helper class for recording compiler metrics.

    Provides a convenient interface matching the WorkflowMetrics pattern.

    Example:
        metrics = get_compiler_metrics()

        with metrics.time_compilation(outcome_id="research-synthesis") as ctx:
            compiled = compiler.compile("research-synthesis")

        metrics.record_execution(status="completed")
    """

    def record_compilation_time(self, outcome_id: str, duration_ms: float) -> None:
        """Record compilation duration (OBS-MET-01)."""
        COMPILER_COMPILATION_TIME_MS.labels(outcome_id=outcome_id).observe(duration_ms)

    @contextmanager
    def time_compilation(self, outcome_id: str) -> Generator[dict[str, float], None, None]:
        """Context manager to time compilation (OBS-MET-01).

        Yields a dict where caller can read elapsed_ms after exit.
        """
        start = time.perf_counter()
        context: dict[str, float] = {}
        try:
            yield context
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            context["elapsed_ms"] = duration_ms
            COMPILER_COMPILATION_TIME_MS.labels(outcome_id=outcome_id).observe(duration_ms)

    def record_node_execution_time(self, node_id: str, node_type: str, duration_ms: float) -> None:
        """Record node execution duration (OBS-MET-02)."""
        COMPILER_NODE_EXECUTION_TIME_MS.labels(node_id=node_id, node_type=node_type).observe(
            duration_ms
        )

    def record_gate_wait_time(self, gate_id: str, duration_ms: float) -> None:
        """Record gate wait duration (OBS-MET-03)."""
        COMPILER_GATE_WAIT_TIME_MS.labels(gate_id=gate_id).observe(duration_ms)

    def record_execution(self, status: str) -> None:
        """Record an execution completion (OBS-MET-04)."""
        COMPILER_EXECUTIONS_TOTAL.labels(status=status).inc()


# Singleton
_instance: CompilerMetrics | None = None


def get_compiler_metrics() -> CompilerMetrics:
    """Get the compiler metrics singleton."""
    global _instance
    if _instance is None:
        _instance = CompilerMetrics()
    return _instance


def reset_compiler_metrics() -> None:
    """Reset singleton (for testing)."""
    global _instance
    _instance = None
