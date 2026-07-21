"""Default + explicit retry-policy resolution for compiled nodes (v0.9.0).

Wires `DAGNode.retry` (parsed by dag_parser.py, never consumed until now -- a dead field)
to LangGraph's own native `RetryPolicy`, which re-invokes a node's entire coroutine on a
retryable exception -- the same "whole-unit re-execution + exponential backoff" convention
Temporal (Activity retries) and AWS Step Functions (Retry/Catch) both use.

Ships a REAL DEFAULT, not opt-in-only: the goal is every consumer of this engine benefits
automatically, not just ones who remember to declare `retry` on every Step.
"""

from __future__ import annotations

from langgraph.types import RetryPolicy, default_retry_on

from sulis_workflows.compiler.dag_parser import DAGNode
from sulis_workflows.domain.errors import PermanentPortError, TransientPortError

# Node types eligible for a DEFAULT retry policy when none is explicitly declared. A gate
# node pauses for a human interrupt -- retrying it makes no sense. Composite/control-flow
# node types (fan_out, routing, route_decider, file_writer, for_each, while) are left
# alone -- narrowly scoped to the two node types that call an adapter port directly.
_DEFAULT_RETRY_TYPES = frozenset({"content", "step"})


def _retry_on(exc: Exception) -> bool:
    """PermanentPortError never retries; TransientPortError always does (the adapter's own
    classification wins, even over LangGraph's default -- e.g. a transient subprocess
    failure that happens to also be an OSError subclass, which LangGraph's own default
    would otherwise refuse). Anything else falls through to LangGraph's own sensible
    default (5xx / connection errors yes; ValueError / OSError / etc no)."""
    if isinstance(exc, PermanentPortError):
        return False
    if isinstance(exc, TransientPortError):
        return True
    return default_retry_on(exc)


def retry_policy_for(node: DAGNode) -> RetryPolicy | None:
    """The RetryPolicy to attach to this node's `add_node()` call, or None for no retry.

    An explicit `node.retry` (parsed from a Step's own declared config) wins --
    `{max_attempts: 0}` opts a node out entirely (e.g. a step with a real side effect that
    must never blindly re-run). Absent an explicit declaration, `content`/`step` nodes get
    the real default described above; other node types get none.
    """
    explicit = node.retry
    if explicit is not None:
        max_attempts = explicit.get("max_attempts")
        if max_attempts == 0:
            return None
        kwargs: dict = {"retry_on": _retry_on}
        if max_attempts is not None:
            kwargs["max_attempts"] = max_attempts
        for key in ("initial_interval", "backoff_factor", "max_interval", "jitter"):
            if key in explicit:
                kwargs[key] = explicit[key]
        return RetryPolicy(**kwargs)

    if node.type in _DEFAULT_RETRY_TYPES:
        return RetryPolicy(max_attempts=3, retry_on=_retry_on)

    return None
