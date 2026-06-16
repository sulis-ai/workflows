"""Fan-out node — Send() dispatch for parallel execution.

Enables C-02 atomicity: all parallel branches dispatched together.
"""

from __future__ import annotations

from langgraph.types import Send


def make_fanout_router(targets: list[str]):
    """Create a fan-out conditional edge function.

    Returns a function (state) -> list[Send] that dispatches
    state to all target nodes in parallel.
    """

    def fanout_router(state: dict) -> list[Send]:
        return [Send(target, state) for target in targets]

    return fanout_router
