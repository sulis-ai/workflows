"""Writing a Tool's output into run state — spec §2.3 (state channels), WP-02 step 5.

Only the `REPLACE` reducer ("last write wins") is implemented here. `MERGE`,
`APPEND` and `UPSERT_BY_ID` all need the channel's *current* value and, for
`UPSERT_BY_ID`, a `key` to match on — real behaviour worth its own tests
against real multi-write scenarios (a loop appending to a list across
iterations, a parallel branch merging into a map), none of which exist yet
in anything this engine can run (no `PARALLEL`/`FOR_EACH` support, no real
loop body that writes to the same channel twice). Writing them now, against
no exercised case, would be guessing at their edge behaviour; a channel
using one of the other three reducers is refused rather than silently
mishandled.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sulis_workflows.definition.model import StateChannel

__all__ = ["UnsupportedReducer", "apply_output"]


class UnsupportedReducer(Exception):
    """Raised when a step's `out` mapping targets a channel whose reducer
    this engine does not yet implement."""

    def __init__(self, *, channel: str, reducer: str) -> None:
        self.channel = channel
        self.reducer = reducer
        super().__init__(
            f"channel {channel!r} uses reducer {reducer!r}, not yet supported"
        )


def apply_output(
    state_channels: Mapping[str, StateChannel],
    current_state: Mapping[str, Any],
    out_mapping: Mapping[str, str],
    tool_output: Mapping[str, Any],
) -> dict[str, Any]:
    """§7.1: `out` maps Tool outputs to channels — `out: { insight: state.insight }`.

    Only a bare `state.<channel>` target (no nested path) is supported, and
    only the `REPLACE` reducer. Raises :class:`UnsupportedReducer` for
    anything else, rather than silently doing the wrong thing.
    """
    new_state = dict(current_state)
    for tool_field, target_path in out_mapping.items():
        if not target_path.startswith("state."):
            continue  # spec allows `out` to target only state.* — schema-enforced (V4)
        channel_name = target_path[len("state.") :]
        channel = state_channels.get(channel_name)
        if channel is not None and channel.reducer != "REPLACE":
            raise UnsupportedReducer(channel=channel_name, reducer=channel.reducer)
        if tool_field in tool_output:
            new_state[channel_name] = tool_output[tool_field]
    return new_state
