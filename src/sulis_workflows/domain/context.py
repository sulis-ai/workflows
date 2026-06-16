"""Invocation context — frozen state carried through a Kind invocation.

The :class:`InvocationContext` is built at the Kind invocation entry point
and read-only thereafter. It carries the platform / run identifiers and
the frozen ``identity_bindings`` (per-port :class:`AdapterIdentity` map)
that the engine guard verifies on every adapter call.

Per ADR-209: there is one identity_bindings set per invocation. The
composition root produces the bindings at startup; the invocation entry
point copies them into the context for the duration of the call. The
engine never mutates the context.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sulis_workflows.domain.identity import AdapterIdentity

__all__ = ["InvocationContext", "MissingCallerIdentity"]


class MissingCallerIdentity(Exception):
    """Raised when an :class:`InvocationContext` is missing the caller ``user_id``.

    Some handler paths (notably the slice-1 ``content.kinds:invoke``
    authz check) require a caller identity for the audit trail. The
    field is optional on the dataclass — system-initiated invocations
    legitimately have no caller — but transports that need a concrete
    identity raise this typed error rather than dereferencing ``None``.

    Per SF-017: replaces the previous ``object.__setattr__(ctx,
    "user_id", ...)`` side-channel pattern.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "InvocationContext.user_id is required for this call but was "
                "absent; the composition root MUST supply the caller's "
                "identity for authz / audit. An absent user_id reaching a "
                "handler that requires it is a wiring bug."
            )
        )


@dataclass(frozen=True)
class InvocationContext:
    """Frozen per-invocation state.

    Attributes:
        platform_id: Tenancy scope (NFR-21).
        run_id: Identifier for the Kind invocation (NFR-11).
        identity_bindings: Port-name → :class:`AdapterIdentity` map. Frozen
            at composition-root construction; the engine verifies every
            adapter call against this map.
        user_id: Caller identity for authz / audit (FR-16, NR-03.1). Optional —
            system-initiated invocations legitimately have no caller. Promoted
            to a first-class field in WP-AUTO-014 per SF-017; the prior
            ``object.__setattr__`` side-channel pattern is forbidden.

    Invariants:
        - identity_bindings MUST be non-empty (a Kind invocation with no
          port bindings cannot perform any adapter call meaningfully; the
          guard would refuse every call regardless).
        - For each entry ``(port_name, identity)`` the binding key MUST
          equal ``identity.port_name`` (a composition-root bug otherwise).
        - The mapping is wrapped in a read-only view to prevent post-
          construction mutation.
    """

    platform_id: str
    run_id: str
    identity_bindings: Mapping[str, AdapterIdentity]
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.identity_bindings:
            raise ValueError(
                "identity_bindings must be non-empty; "
                "a Kind invocation must bind at least one port at the "
                "composition root"
            )
        for port_name, identity in self.identity_bindings.items():
            if identity.port_name != port_name:
                raise ValueError(
                    "identity_bindings key disagrees with identity.port_name: "
                    f"binding key {port_name!r} vs identity.port_name "
                    f"{identity.port_name!r}"
                )

        # Wrap in a read-only mapping view so callers cannot mutate the
        # bindings dict through the frozen-dataclass field.
        object.__setattr__(
            self,
            "identity_bindings",
            MappingProxyType(dict(self.identity_bindings)),
        )
