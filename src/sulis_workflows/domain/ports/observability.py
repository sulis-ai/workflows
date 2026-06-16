"""ObservabilityPort — fire-and-forget instrumentation channel (WP-8).

The workflow service emits one event per primitive call, stage entry /
exit, Verdict, classification, five-whys iteration, terminal state,
side-by-side comparison record, breaker state change, sandbox audit and
adapter-identity audit. Every event is tagged with the tenancy keys
``platform_id`` (NFR-21) and ``run_id`` (NFR-11) so downstream
correlators can join records across pipelines (NFR-12 side-by-side
comparison).

Per TDD §4.7 and the WP-8 Contract:

- ``emit()`` is fire-and-forget. Adapter failure does NOT propagate up.
  The bulkhead is the adapter's own retry budget (see
  ``infrastructure.observability.pubsub_observability``).
- A single Kind invocation produces one root ``run_id``; nested
  primitive events carry the same ``platform_id`` + the parent's
  ``run_id`` as ``parent_run_id``.
- The event-class string is constrained to the ten classes named in
  TDD §4.7. Other strings are rejected at construction time.
- The port lives in the workflow domain core. The adapter
  implementation (PubSub-backed) lives in ``infrastructure/``.

This module ships:

- ``ObservabilityEvent`` — frozen dataclass carrying the event payload.
- ``ObservabilityPort`` — runtime-checkable Protocol.
- ``OBSERVABILITY_EVENT_CLASSES`` — the authoritative tuple of accepted
  event-class strings.
- ``ObservabilityRecord`` — what a recording adapter (the in-memory
  test double) stores per emit.
- ``InMemoryObservabilityRecorder`` — unit-mode adapter; the PubSub
  adapter is wired separately in ``infrastructure/observability``.
- ``FailingObservabilityAdapter`` — test double that always fails its
  internal publish; used to verify the fire-and-forget contract.
- ``with_child_run_id`` — helper producing a child context with the
  parent's ``run_id`` propagated as ``parent_run_id``.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "OBSERVABILITY_EVENT_CLASSES",
    "FailingObservabilityAdapter",
    "InMemoryObservabilityRecorder",
    "ObservabilityEvent",
    "ObservabilityPort",
    "ObservabilityRecord",
    "PlatformId",
    "RunId",
    "stage_lifecycle",
    "with_child_run_id",
]


# Type aliases for the tenancy keys. The WP Contract names them
# ``PlatformId`` and ``RunId``; the existing :class:`InvocationContext`
# carries them as plain ``str``. The aliases document intent without
# constraining call sites.
PlatformId = str
RunId = str


# Authoritative event-class set from TDD §4.7. The order matches the
# §4.7 table top-to-bottom for readability; the recorder uses a set
# membership check that ignores order.
OBSERVABILITY_EVENT_CLASSES: tuple[str, ...] = (
    "stage_primitive_call",
    "stage_lifecycle",
    "verdict_emitted",
    "verdict_classified",
    "five_whys_step",
    "kind_terminal",
    "pipeline_comparison_record",
    "breaker_state_change",
    "sandbox_violation_audit",
    "adapter_identity_mismatch",
)


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObservabilityEvent:
    """One instrumentation event.

    Attributes:
        event_class: One of :data:`OBSERVABILITY_EVENT_CLASSES`.
        payload: Event-class-specific shape. Adapters serialise this
            dict; the port does not constrain its inner structure
            beyond JSON-serialisability (left to the adapter).
        parent_run_id: When the event was emitted from inside a nested
            stage / primitive call, the parent invocation's ``run_id``.
            None for root events.

    Invariants:
        - ``event_class`` MUST be a known class (rejected otherwise).
        - The dataclass is frozen so callers cannot mutate events
          after enqueue.
    """

    event_class: str
    payload: dict[str, Any]
    parent_run_id: RunId | None

    def __post_init__(self) -> None:
        if self.event_class not in OBSERVABILITY_EVENT_CLASSES:
            raise ValueError(
                f"unknown event_class {self.event_class!r}; "
                f"must be one of {sorted(OBSERVABILITY_EVENT_CLASSES)}"
            )


@dataclass(frozen=True)
class ObservabilityRecord:
    """A recorded emission — what the in-memory recorder stores.

    Carries the tenancy keys alongside the event for assertion in tests
    and for downstream side-by-side comparison joins (NFR-12).
    """

    event: ObservabilityEvent
    platform_id: PlatformId
    run_id: RunId


@runtime_checkable
class ObservabilityPort(Protocol):
    """Fire-and-forget instrumentation channel.

    Contract (TDD §5.1):

    - ``platform_id`` and ``run_id`` are required at the call site.
    - Failure inside the adapter MUST NOT propagate up; the caller
      sees a successful return regardless of whether publication
      succeeded.
    - The adapter MUST accept all ten event classes named in
      :data:`OBSERVABILITY_EVENT_CLASSES` without rejection.
    """

    async def emit(
        self,
        event: ObservabilityEvent,
        *,
        platform_id: PlatformId,
        run_id: RunId,
    ) -> None: ...


@dataclass
class InMemoryObservabilityRecorder:
    """In-process adapter for unit tests + composition-root local dev.

    Records every emission in an ordered list. Production adapters
    publish to PubSub via the infrastructure wrapper.
    """

    _records: list[ObservabilityRecord] = field(default_factory=list)

    async def emit(
        self,
        event: ObservabilityEvent,
        *,
        platform_id: PlatformId,
        run_id: RunId,
    ) -> None:
        """Record the event. Never raises.

        Inputs are validated by :class:`ObservabilityEvent` itself; if
        construction succeeded the event is safe to record.
        """
        self._records.append(
            ObservabilityRecord(
                event=event,
                platform_id=platform_id,
                run_id=run_id,
            )
        )

    @property
    def records(self) -> list[ObservabilityRecord]:
        """Read-only snapshot of recorded emissions.

        Returns a copy so callers cannot mutate the underlying list.
        """
        return list(self._records)


@dataclass
class FailingObservabilityAdapter:
    """Test double that always fails its internal publish.

    Exists to verify the fire-and-forget contract: a real adapter
    whose internal publication raises must NOT surface the exception
    to the caller. The recorder is too forgiving to express this
    invariant on its own.
    """

    attempted_emits: int = 0

    async def emit(
        self,
        event: ObservabilityEvent,
        *,
        platform_id: PlatformId,
        run_id: RunId,
    ) -> None:
        """Increment the attempt counter, then swallow a simulated
        publication failure. The caller sees a successful return.
        """
        self.attempted_emits += 1
        try:
            # Simulate an adapter-internal failure (e.g. PubSub
            # publish timeout, network unreachable).
            raise RuntimeError("simulated adapter publication failure")
        except Exception:
            # Fire-and-forget: log locally, drop the event, return.
            _logger.debug(
                "observability adapter publish failed; dropped",
                extra={
                    "platform_id": platform_id,
                    "run_id": run_id,
                    "event_class": event.event_class,
                },
            )


@asynccontextmanager
async def stage_lifecycle(
    port: ObservabilityPort,
    *,
    stage_name: str,
    platform_id: PlatformId,
    run_id: RunId,
    parent_run_id: RunId | None = None,
):
    """Emit ``stage_lifecycle`` entry + exit events around a stage call.

    Extracts the shared shape every stage call site would otherwise
    duplicate (build entry event → emit → run stage → measure duration
    → build exit event → emit). The exit event's ``status`` reflects
    whether the body raised.

    Usage::

        async with stage_lifecycle(
            port,
            stage_name="find",
            platform_id=ctx.platform_id,
            run_id=ctx.run_id,
        ):
            await run_find_stage(...)

    Per TDD §4.7 the ``stage_lifecycle`` event carries
    ``{stage_name, duration_ms, status, platform_id, run_id}``. The
    entry event has ``status="entered"`` and ``duration_ms=0``; the
    exit event has ``status="ok"`` or ``status="error"`` and the
    elapsed wall-clock duration.

    Fire-and-forget semantics still hold: emit failures inside the
    helper are absorbed by the port's adapter contract — they do not
    propagate out of this context manager.
    """
    entry_event = ObservabilityEvent(
        event_class="stage_lifecycle",
        payload={
            "stage_name": stage_name,
            "duration_ms": 0,
            "status": "entered",
        },
        parent_run_id=parent_run_id,
    )
    await port.emit(entry_event, platform_id=platform_id, run_id=run_id)

    start = time.monotonic()
    status = "ok"
    try:
        yield
    except BaseException:
        status = "error"
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        exit_event = ObservabilityEvent(
            event_class="stage_lifecycle",
            payload={
                "stage_name": stage_name,
                "duration_ms": duration_ms,
                "status": status,
            },
            parent_run_id=parent_run_id,
        )
        await port.emit(exit_event, platform_id=platform_id, run_id=run_id)


def with_child_run_id(
    parent_ctx: dict[str, Any],
    *,
    child_run_id: RunId,
) -> dict[str, Any]:
    """Produce a child invocation context with parent_run_id propagated.

    A nested stage / primitive call needs:

    - The same ``platform_id`` as its parent (tenancy is invariant
      within a Kind invocation tree).
    - A fresh ``run_id`` identifying the nested call.
    - ``parent_run_id`` set to the parent's ``run_id`` so downstream
      consumers can stitch the tree.

    Args:
        parent_ctx: Dict carrying at least ``platform_id`` + ``run_id``.
        child_run_id: The new ``run_id`` for the nested context.

    Returns:
        A new dict (parent is not mutated) carrying the propagated
        keys plus ``parent_run_id``.

    Raises:
        KeyError: when ``parent_ctx`` is missing ``platform_id`` or
            ``run_id``.
    """
    return {
        "platform_id": parent_ctx["platform_id"],
        "run_id": child_run_id,
        "parent_run_id": parent_ctx["run_id"],
    }
