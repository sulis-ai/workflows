"""RecordsPort — durable, write-once attempt records (spec §12.2).

Every attempt of every node is one write-once record keyed by
(run, scope, node, attempt): inputs used, output, control results, verdict
or error, who/what performed it, and start/end times. Loop counters, retry
counts and progress are derived from records, never held in memory — this
is what makes next(run, scope) stateless (§12.1).
"""

from __future__ import annotations

import asyncio

import pytest

from sulis_workflows.domain.ports.records import (
    AttemptKey,
    AttemptRecord,
    DuplicateAttempt,
    RecordsPort,
    StubRecordsAdapter,
)


def _record(**overrides) -> AttemptRecord:
    defaults = {
        "key": AttemptKey(run="run-1", scope="root", node="interrogate", attempt=1),
        "inputs": {"question": "why"},
        "output": {"insights": []},
        "control_results": [],
        "verdict": None,
        "performed_by": "AGENT:interrogate@1",
        "started_at": "2026-09-17T09:00:00Z",
        "ended_at": "2026-09-17T09:00:01Z",
    }
    defaults.update(overrides)
    return AttemptRecord(**defaults)


def test_stub_adapter_satisfies_the_port():
    assert isinstance(StubRecordsAdapter(), RecordsPort)


def test_record_then_read_back():
    records = StubRecordsAdapter()
    rec = _record()
    asyncio.run(records.record_attempt(rec, platform_id="tenant-1", run_id="run-1"))
    got = asyncio.run(
        records.get_attempts(
            "run-1", "root", "interrogate", platform_id="tenant-1", run_id="run-1"
        )
    )
    assert got == [rec]


def test_write_once_a_second_write_to_the_same_key_is_refused():
    records = StubRecordsAdapter()
    rec = _record()
    asyncio.run(records.record_attempt(rec, platform_id="tenant-1", run_id="run-1"))
    with pytest.raises(DuplicateAttempt):
        asyncio.run(records.record_attempt(rec, platform_id="tenant-1", run_id="run-1"))


def test_a_second_attempt_number_is_a_new_key_not_a_duplicate():
    records = StubRecordsAdapter()
    first = _record(
        key=AttemptKey(run="run-1", scope="root", node="interrogate", attempt=1)
    )
    second = _record(
        key=AttemptKey(run="run-1", scope="root", node="interrogate", attempt=2)
    )
    asyncio.run(records.record_attempt(first, platform_id="tenant-1", run_id="run-1"))
    asyncio.run(records.record_attempt(second, platform_id="tenant-1", run_id="run-1"))
    got = asyncio.run(
        records.get_attempts(
            "run-1", "root", "interrogate", platform_id="tenant-1", run_id="run-1"
        )
    )
    assert [r.key.attempt for r in got] == [1, 2]


def test_get_attempts_on_an_unwritten_key_is_empty_not_an_error():
    records = StubRecordsAdapter()
    got = asyncio.run(
        records.get_attempts(
            "run-1", "root", "nonexistent", platform_id="tenant-1", run_id="run-1"
        )
    )
    assert got == []


def test_records_are_scoped_by_run_not_shared_across_runs():
    records = StubRecordsAdapter()
    asyncio.run(
        records.record_attempt(
            _record(
                key=AttemptKey(run="run-1", scope="root", node="interrogate", attempt=1)
            ),
            platform_id="tenant-1",
            run_id="run-1",
        )
    )
    got = asyncio.run(
        records.get_attempts(
            "run-2", "root", "interrogate", platform_id="tenant-1", run_id="run-2"
        )
    )
    assert got == []


def test_tenancy_propagated_to_the_adapter():
    records = StubRecordsAdapter()
    asyncio.run(
        records.record_attempt(_record(), platform_id="tenant-1", run_id="run-1")
    )
    assert records.observed_calls == [("tenant-1", "run-1")]
