"""Routing node — conditional branching based on state.

Routes to exactly one target based on a state field value.
"""

from __future__ import annotations


def make_routing_edge(node_id: str, routes: dict[str, str], route_key: str):
    """Create a conditional routing edge function.

    Args:
        node_id: The routing node ID.
        routes: Mapping of state field values to target node IDs.
        route_key: The state field to inspect for routing.

    Returns a function (state) -> str that returns the target node ID.
    """

    def routing_fn(state: dict) -> str:
        value = state.get("step_outputs", {}).get(node_id, {}).get(route_key, "")
        if value in routes:
            return routes[value]
        # Default to first route if no match
        return next(iter(routes.values()))

    return routing_fn
