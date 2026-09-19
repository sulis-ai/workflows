"""Writing a Tool's output into run state — spec §2.3 (state channels), WP-02 step 5.

All four reducers spec §2.3 names are implemented here, grounded exactly in its own
words: "`REPLACE` (last write wins), `MERGE` (maps, shallow), `APPEND` (lists),
`UPSERT_BY_ID` (lists of objects, replaced by `key`)." The same sentence also states
the failure mode this module defends against: "A write that does not match the
channel type is refused and recorded as a failed attempt" — `ReducerMismatch` is
that refusal (the caller, `engine/run.py`, is what actually records it as a failed
attempt rather than applying it, per D19).

Every channel's own `type` is schema-closed to `list<T>` (APPEND, UPSERT_BY_ID),
`map<T>` (MERGE) or anything (REPLACE) at V1 — see `schema/process.v1.schema.json`'s
`state_channel` — so the shape checks here are the runtime half of a contract the
schema only partly enforces (it cannot check a *value*, only a declared type string).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sulis_workflows.definition.model import StateChannel

__all__ = ["ReducerMismatch", "apply_output"]


class ReducerMismatch(Exception):
    """A Tool's output does not match its target channel's reducer shape —
    spec §2.3: "a write that does not match the channel type is refused
    and recorded as a failed attempt." Never applied silently."""

    def __init__(self, *, channel: str, reducer: str, reason: str) -> None:
        self.channel = channel
        self.reducer = reducer
        self.reason = reason
        super().__init__(f"channel {channel!r} ({reducer}): {reason}")


def apply_output(
    state_channels: Mapping[str, StateChannel],
    current_state: Mapping[str, Any],
    out_mapping: Mapping[str, str],
    tool_output: Mapping[str, Any],
) -> dict[str, Any]:
    """§7.1: `out` maps Tool outputs to channels — `out: { insight: state.insight }`.

    Only a bare `state.<channel>` target (no nested path) is supported (schema-
    enforced, V4). Raises :class:`ReducerMismatch` for a value that does not fit
    its channel's reducer shape, rather than applying it or crashing uncaught.
    """
    new_state = dict(current_state)
    for tool_field, target_path in out_mapping.items():
        if not target_path.startswith("state."):
            continue  # spec allows `out` to target only state.* — schema-enforced (V4)
        channel_name = target_path[len("state.") :]
        if tool_field not in tool_output:
            continue
        value = tool_output[tool_field]
        channel = state_channels.get(channel_name)
        reducer = channel.reducer if channel is not None else "REPLACE"
        new_state[channel_name] = _reduce(
            channel_name, reducer, channel, new_state.get(channel_name), value
        )
    return new_state


def _reduce(
    channel_name: str,
    reducer: str,
    channel: StateChannel | None,
    current_value: Any,
    value: Any,
) -> Any:
    if reducer == "REPLACE":
        return value

    if reducer == "MERGE":
        if not isinstance(value, Mapping):
            raise ReducerMismatch(
                channel=channel_name,
                reducer=reducer,
                reason=f"write is {_type_name(value)}, not an object (§2.3: MERGE is maps, shallow)",
            )
        merged: dict[str, Any] = (
            dict(current_value) if isinstance(current_value, Mapping) else {}
        )
        merged.update(value)
        return merged

    if reducer == "APPEND":
        if not isinstance(value, list):
            raise ReducerMismatch(
                channel=channel_name,
                reducer=reducer,
                reason=f"write is {_type_name(value)}, not a list (§2.3: APPEND is lists)",
            )
        base: list[Any] = list(current_value) if isinstance(current_value, list) else []
        return base + value

    if reducer == "UPSERT_BY_ID":
        if not isinstance(value, list):
            raise ReducerMismatch(
                channel=channel_name,
                reducer=reducer,
                reason=(
                    f"write is {_type_name(value)}, not a list "
                    "(§2.3: UPSERT_BY_ID is lists of objects)"
                ),
            )
        key = channel.key if channel is not None else None
        if not key:
            # V16 refuses this at validation time already; a channel that
            # somehow reaches the engine without one is refused here too
            # rather than upserting on an undefined identity.
            raise ReducerMismatch(
                channel=channel_name,
                reducer=reducer,
                reason="channel declares no `key` to upsert by (V16 should have refused this)",
            )
        items: list[Any] = (
            list(current_value) if isinstance(current_value, list) else []
        )
        by_key = {
            item[key]: index
            for index, item in enumerate(items)
            if isinstance(item, Mapping) and key in item
        }
        for item in value:
            if not isinstance(item, Mapping) or key not in item:
                raise ReducerMismatch(
                    channel=channel_name,
                    reducer=reducer,
                    reason=(
                        f"an item in the write is not an object with a {key!r} field "
                        "(§2.3: UPSERT_BY_ID is lists of objects, replaced by key)"
                    ),
                )
            existing_index = by_key.get(item[key])
            if existing_index is None:
                by_key[item[key]] = len(items)
                items.append(item)
            else:
                items[existing_index] = item
        return items

    raise AssertionError(  # unreachable: reducer is schema-closed to the four above (V1)
        f"channel {channel_name!r} declares reducer {reducer!r}, outside the closed set"
    )


def _type_name(value: Any) -> str:
    return type(value).__name__
