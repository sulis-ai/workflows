"""Adapter identity, frozen at composition-root construction (ADR-209).

Every adapter the workflow service uses (LLM, content storage, tool dispatch,
execution runtime, checkpointing, observability) carries an :class:`AdapterIdentity`
that the engine verifies on every adapter call.

Identity is built once per adapter at composition-root construction; it is
read at startup, never re-read mid-flight, and participates in the
run-identity tag (per ADR-206) when Verdicts and checkpoints are signed.

Design constraints (ADR-209 + TDD §3.5 lints L9/L10):

- ``config_fingerprint`` is deterministic. Same config → same fingerprint.
  No timestamps, random nonces, PID, or hostname feed the fingerprint.
- Identity is immutable after construction (``frozen=True``).
- The engine guard (:func:`verify_adapter_identity`) refuses calls whose
  reported identity differs from the active :class:`InvocationContext`'s
  ``identity_bindings`` and emits an ``adapter_identity_mismatch`` audit
  event.
- This module sits in the workflow domain core: no SDK imports, no
  environment reads, no infrastructure dependencies.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sulis_workflows.domain.context import InvocationContext
    from sulis_workflows.domain.identity_audit import IdentityAuditSink


__all__ = [
    "AdapterIdentity",
    "AdapterIdentityMismatch",
    "IdentifiedAdapter",
    "compute_config_fingerprint",
    "verify_adapter_identity",
]


_FINGERPRINT_HEX_LEN = 64  # SHA-256 in hex


@dataclass(frozen=True)
class AdapterIdentity:
    """Stable identity for an adapter instance.

    Frozen at composition-root construction. Carried in InvocationContext.
    Verified on every adapter call.

    Attributes:
        adapter_class: Fully qualified class name, e.g. ``"AnthropicAdapter"``.
        config_fingerprint: Deterministic SHA-256 (64-char hex) of frozen
            config values that affect adapter behaviour. MUST NOT include
            secrets, timestamps, random nonces, PID, or hostname.
        port_name: The port this adapter implements, e.g. ``"LLMPort"``.
    """

    adapter_class: str
    config_fingerprint: str
    port_name: str

    def __post_init__(self) -> None:
        if not self.adapter_class:
            raise ValueError("adapter_class must be non-empty")
        if len(self.config_fingerprint) != _FINGERPRINT_HEX_LEN:
            raise ValueError(
                "config_fingerprint must be a 64-char hex SHA-256, "
                f"got {len(self.config_fingerprint)} chars"
            )
        if not self.port_name:
            raise ValueError("port_name must be non-empty")

    def matches(self, other: AdapterIdentity) -> bool:
        """Equivalent to ``self == other``; spelled out for engine readability."""
        return self == other


@runtime_checkable
class IdentifiedAdapter(Protocol):
    """Protocol every adapter behind a workflow-service port must implement.

    The engine reads ``.identity`` on every adapter call and compares it
    against the active :class:`InvocationContext`'s
    ``identity_bindings[port_name]``. Repeated reads MUST return the same
    value (contract test ``test_adapter_identity_stable_across_calls``).
    """

    @property
    def identity(self) -> AdapterIdentity: ...


class AdapterIdentityMismatch(Exception):
    """Raised when an adapter's reported identity differs from the active
    invocation context's bindings.

    Surfaces operationally as ``stopped_by_technical_fatal`` (per FR-9 +
    ADR-209). Carries the offending port and the (expected, observed) pair
    so audit consumers can correlate.
    """

    def __init__(
        self,
        *,
        port_name: str,
        expected: AdapterIdentity | None,
        observed: AdapterIdentity,
    ) -> None:
        self.port_name = port_name
        self.expected = expected
        self.observed = observed
        if expected is None:
            msg = (
                f"adapter identity mismatch on {port_name!r}: "
                f"no binding in invocation context; "
                f"observed {observed.adapter_class!r}"
            )
        else:
            msg = (
                f"adapter identity mismatch on {port_name!r}: "
                f"expected {expected.adapter_class!r}, "
                f"observed {observed.adapter_class!r}"
            )
        super().__init__(msg)


def compute_config_fingerprint(config: dict[str, object]) -> str:
    """Compute the deterministic 64-char hex SHA-256 of a config dict.

    The fingerprint is independent of key insertion order: the dict is
    serialised with ``sort_keys=True``. Values must be JSON-serialisable.

    Per ADR-209: the fingerprint covers configuration that affects
    behaviour (model name, base URL, timeout) but NOT credentials.
    Composition-root code is responsible for choosing the input keys.

    Per TDD §3.5 lint L10: this function must be deterministic. Repeated
    calls with the same input produce the same output. No timestamps,
    random nonces, PID, or hostname are mixed in. The unit test
    ``test_repeated_construction_with_same_inputs_yields_same_fingerprint``
    enforces this contract at the runtime level.
    """
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_adapter_identity(
    *,
    adapter: IdentifiedAdapter,
    port_name: str,
    context: InvocationContext,
    audit_sink: IdentityAuditSink,
) -> None:
    """Verify an adapter's reported identity against the invocation context.

    Single guard at the port-invocation boundary. On mismatch, raises
    :class:`AdapterIdentityMismatch` AFTER emitting an
    ``adapter_identity_mismatch`` audit event via ``audit_sink``.

    The 'no binding' case (port_name absent from context.identity_bindings)
    is a mismatch: a Kind invocation that never bound this port cannot
    legitimately reach an adapter call for it.

    Args:
        adapter: The adapter instance whose ``.identity`` is being checked.
        port_name: The port name the call is being routed through.
        context: The active :class:`InvocationContext` carrying the frozen
            identity bindings for this Kind invocation.
        audit_sink: Sink for the ``adapter_identity_mismatch`` audit event.
            Called only on mismatch.

    Raises:
        AdapterIdentityMismatch: when the reported identity differs from
            the bindings, or when no binding exists for ``port_name``.
    """
    # Local import to avoid an import cycle with identity_audit which itself
    # references AdapterIdentity for typing.
    from sulis_workflows.domain.identity_audit import IdentityMismatchEvent

    observed = adapter.identity
    expected = context.identity_bindings.get(port_name)

    if expected is not None and expected.matches(observed):
        return

    event = IdentityMismatchEvent(
        port_name=port_name,
        expected=expected,
        observed=observed,
        platform_id=context.platform_id,
        run_id=context.run_id,
    )
    audit_sink.emit(event)
    raise AdapterIdentityMismatch(
        port_name=port_name,
        expected=expected,
        observed=observed,
    )
