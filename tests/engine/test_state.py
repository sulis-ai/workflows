"""engine/state.py — the four reducers spec §2.3 names, and the bad-but-conformant
write each one must refuse rather than apply (D19)."""

from __future__ import annotations

import pytest

from sulis_workflows.definition.model import StateChannel
from sulis_workflows.engine.state import ReducerMismatch, apply_output


def _channels(**channels: StateChannel) -> dict[str, StateChannel]:
    return channels


# --------------------------------------------------------------------------- REPLACE --


def test_replace_last_write_wins() -> None:
    channels = _channels(status=StateChannel(type="string", reducer="REPLACE"))
    state = apply_output(
        channels, {"status": "OLD"}, {"status": "state.status"}, {"status": "NEW"}
    )
    assert state["status"] == "NEW"


# ----------------------------------------------------------------------------- MERGE --


def test_merge_shallow_merges_new_keys_over_old() -> None:
    channels = _channels(meta=StateChannel(type="map<any>", reducer="MERGE"))
    state = apply_output(
        channels,
        {"meta": {"a": 1, "b": 2}},
        {"meta": "state.meta"},
        {"meta": {"b": 20, "c": 3}},
    )
    assert state["meta"] == {"a": 1, "b": 20, "c": 3}


def test_merge_with_no_current_value_starts_empty() -> None:
    channels = _channels(meta=StateChannel(type="map<any>", reducer="MERGE"))
    state = apply_output(channels, {}, {"meta": "state.meta"}, {"meta": {"a": 1}})
    assert state["meta"] == {"a": 1}


def test_merge_refuses_a_non_object_write() -> None:
    """Bad-but-conformant: a MERGE channel written a bare list."""
    channels = _channels(meta=StateChannel(type="map<any>", reducer="MERGE"))
    with pytest.raises(ReducerMismatch, match="meta"):
        apply_output(
            channels,
            {"meta": {}},
            {"meta": "state.meta"},
            {"meta": ["not", "a", "map"]},
        )


# ---------------------------------------------------------------------------- APPEND --


def test_append_extends_the_existing_list() -> None:
    channels = _channels(notes=StateChannel(type="list<string>", reducer="APPEND"))
    state = apply_output(
        channels,
        {"notes": ["first"]},
        {"notes": "state.notes"},
        {"notes": ["second", "third"]},
    )
    assert state["notes"] == ["first", "second", "third"]


def test_append_with_no_current_value_starts_empty() -> None:
    channels = _channels(notes=StateChannel(type="list<string>", reducer="APPEND"))
    state = apply_output(channels, {}, {"notes": "state.notes"}, {"notes": ["only"]})
    assert state["notes"] == ["only"]


def test_append_refuses_a_non_list_write() -> None:
    """Bad-but-conformant: a Tool whose output field is typed as a list but
    a single write hands the engine a bare scalar instead of `[scalar]`."""
    channels = _channels(notes=StateChannel(type="list<string>", reducer="APPEND"))
    with pytest.raises(ReducerMismatch, match="notes"):
        apply_output(
            channels,
            {"notes": []},
            {"notes": "state.notes"},
            {"notes": "just one note"},
        )


# ------------------------------------------------------------------------ UPSERT_BY_ID --


def test_upsert_by_id_inserts_new_and_replaces_matching() -> None:
    channels = _channels(
        insights=StateChannel(type="list<any>", reducer="UPSERT_BY_ID", key="id")
    )
    current = {
        "insights": [{"id": "i1", "claim": "old claim"}, {"id": "i2", "claim": "keep"}]
    }
    state = apply_output(
        channels,
        current,
        {"insights": "state.insights"},
        {
            "insights": [
                {"id": "i1", "claim": "revised claim"},
                {"id": "i3", "claim": "new"},
            ]
        },
    )
    by_id = {item["id"]: item["claim"] for item in state["insights"]}
    assert by_id == {"i1": "revised claim", "i2": "keep", "i3": "new"}
    # order: existing items keep their position, new ones append at the end
    assert [item["id"] for item in state["insights"]] == ["i1", "i2", "i3"]


def test_upsert_by_id_with_no_current_value_starts_empty() -> None:
    channels = _channels(
        insights=StateChannel(type="list<any>", reducer="UPSERT_BY_ID", key="id")
    )
    state = apply_output(
        channels,
        {},
        {"insights": "state.insights"},
        {"insights": [{"id": "i1", "claim": "a"}]},
    )
    assert state["insights"] == [{"id": "i1", "claim": "a"}]


def test_upsert_by_id_refuses_a_non_list_write() -> None:
    channels = _channels(
        insights=StateChannel(type="list<any>", reducer="UPSERT_BY_ID", key="id")
    )
    with pytest.raises(ReducerMismatch, match="insights"):
        apply_output(
            channels,
            {"insights": []},
            {"insights": "state.insights"},
            {"insights": {"id": "i1"}},
        )


def test_upsert_by_id_refuses_an_item_with_no_key_field() -> None:
    """Bad-but-conformant: a list of objects, but one item is missing the
    field the channel itself declares as its `key` — not upsertable."""
    channels = _channels(
        insights=StateChannel(type="list<any>", reducer="UPSERT_BY_ID", key="id")
    )
    with pytest.raises(ReducerMismatch, match="insights"):
        apply_output(
            channels,
            {"insights": []},
            {"insights": "state.insights"},
            {"insights": [{"claim": "no id here"}]},
        )


def test_upsert_by_id_refuses_a_channel_with_no_key() -> None:
    """V16 refuses this at validation time; the engine refuses it too if it
    somehow still reaches here, rather than upserting on an undefined identity."""
    channels = _channels(
        insights=StateChannel(type="list<any>", reducer="UPSERT_BY_ID")
    )
    with pytest.raises(ReducerMismatch, match="insights"):
        apply_output(
            channels,
            {"insights": []},
            {"insights": "state.insights"},
            {"insights": [{"id": "i1"}]},
        )
