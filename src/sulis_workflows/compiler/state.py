"""Typed state schema for compiled OFM graphs.

Provides OFMGraphState (TypedDict) as the state schema for all compiled
LangGraph StateGraph instances. Fields mutated by parallel fan-out branches
use Annotated with reducer functions to ensure correct state merging.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer for dict fields: merge right into left."""
    return {**left, **right}


class OFMGraphState(TypedDict):
    """Typed state schema for compiled OFM graphs.

    Carries execution context through the graph. Each node
    reads from and writes to this state via its return value.

    Fields mutated by parallel branches (fan-out via Send()) MUST use
    Annotated with a reducer function. Without reducers, parallel node
    outputs silently overwrite each other instead of merging.
    """

    # Identity
    execution_id: str
    outcome_id: str

    # Progress tracking
    phase: str
    completed_nodes: Annotated[list[str], operator.add]

    # Data flow — reducers merge parallel outputs
    step_outputs: Annotated[dict[str, Any], _merge_dicts]
    gate_decisions: Annotated[dict[str, str], _merge_dicts]

    # Metadata
    metadata: dict[str, Any]
