"""PolicyPort — permission-first, before every dispatch (WP-02).

Spec §10.1: "Before the engine starts a run, dispatches any Tool, or accepts
any decision, it asks the host's PolicyPort whether the acting identity ...
holds the required permission." This is the seam sulis-ai/platform ADR-022
found missing from the published engine: the platform's in-app engine
enforces an action's declared permission before dispatch and the published
engine does not. The port is part of the engine contract, not an option.

The verdict vocabulary is ADR-028's — PERMIT | DENY | INDETERMINATE — used
uniformly rather than a bespoke boolean, per CLAUDE.md's "hold conventions
once". §10.1 describes a binary outcome (permitted or refused); an engine
acting on this port treats anything other than PERMIT as a refusal
(§10.1: "A refusal records the attempt as FORBIDDEN"), so INDETERMINATE
fails closed here exactly as DENY does.

Permission strings are the host's grammar (ADR-024, e.g. platform strings
follow `<service>.<resource>.<verb>`); this port carries them opaquely and
never validates their shape — the host does that at publish time.

`evaluate_policy` is the second, distinct use §7.6 names: a GATE's
`policy:` decider, which asks the host to evaluate a *named policy*
(a POLICY-kind Control document, §5.1 — "who or what may do or permit
something") against the gate's `reviewing` values, rather than checking a
bare permission string. Deliberately deferred until WP-02 step 4 needed
it, rather than guessed at in step 1 (`docs/runs/` step 1's own decision
record).

Shape follows the established sibling ports (LLMPort, ToolDispatchPort,
CheckpointingPort): a runtime_checkable Protocol extending
IdentifiedAdapter, tenancy keys (platform_id/run_id) on every call, and an
in-memory stub for contract tests.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "PolicyDecision",
    "PolicyPort",
    "StubPolicyAdapter",
    "Verdict",
]


class Verdict(str, Enum):
    """ADR-028's decision vocabulary. No fourth value, no boolean stand-in."""

    PERMIT = "PERMIT"
    DENY = "DENY"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class PolicyDecision:
    """The PolicyPort's answer to one authorization question.

    ``rationale`` is optional on PERMIT (nothing to explain) but SHOULD be
    present on DENY/INDETERMINATE — it is what the engine's FORBIDDEN
    record (§10.1) and a gate's provenance trail (§7.6) both carry forward.
    """

    verdict: Verdict
    rationale: str | None = None


@runtime_checkable
class PolicyPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic authorization protocol (§10.1).

    ``authorize`` asks whether ``identity`` holds ``permission`` for this
    run. Called before the engine starts a run, before it dispatches any
    Tool, and before it accepts any decision — never skipped, never
    cached across calls (the run's identity and the permission both vary
    per call).

    Error contract: an adapter SHOULD raise
    ``sulis_workflows.domain.errors.TransientPortError`` for a failure a
    retry might fix (the policy backend is unreachable) and
    ``PermanentPortError`` for one it won't (the permission string is
    malformed). Raising neither is equivalent to answering
    ``INDETERMINATE`` — the engine still fails closed.
    """

    async def authorize(
        self,
        permission: str,
        *,
        identity: str,
        platform_id: str,
        run_id: str,
    ) -> PolicyDecision: ...

    async def evaluate_policy(
        self,
        ref: str,
        *,
        reviewing: Mapping[str, Any],
        identity: str,
        platform_id: str,
        run_id: str,
    ) -> PolicyDecision: ...


@dataclass
class StubPolicyAdapter:
    """In-memory stub for unit-mode contract tests.

    Permits everything by default. ``denies``/``indeterminate`` seed
    specific permission strings for ``authorize``; ``policy_denies``/
    ``policy_indeterminate`` do the same for ``evaluate_policy``'s control
    refs — separate sets, since a permission string and a policy control
    ref share no namespace and seeding them together would let a test pass
    by accident.
    """

    denies: set[str] = field(default_factory=set)
    indeterminate: set[str] = field(default_factory=set)
    policy_denies: set[str] = field(default_factory=set)
    policy_indeterminate: set[str] = field(default_factory=set)
    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubPolicyAdapter",
            port_name="PolicyPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def authorize(
        self,
        permission: str,
        *,
        identity: str,
        platform_id: str,
        run_id: str,
    ) -> PolicyDecision:
        self.observed_calls.append((platform_id, run_id))
        if permission in self.denies:
            return PolicyDecision(
                verdict=Verdict.DENY,
                rationale=f"stub-denied:{permission}",
            )
        if permission in self.indeterminate:
            return PolicyDecision(
                verdict=Verdict.INDETERMINATE,
                rationale=f"stub-indeterminate:{permission}",
            )
        return PolicyDecision(verdict=Verdict.PERMIT)

    async def evaluate_policy(
        self,
        ref: str,
        *,
        reviewing: Mapping[str, Any],
        identity: str,
        platform_id: str,
        run_id: str,
    ) -> PolicyDecision:
        self.observed_calls.append((platform_id, run_id))
        if ref in self.policy_denies:
            return PolicyDecision(verdict=Verdict.DENY, rationale=f"stub-denied:{ref}")
        if ref in self.policy_indeterminate:
            return PolicyDecision(
                verdict=Verdict.INDETERMINATE, rationale=f"stub-indeterminate:{ref}"
            )
        return PolicyDecision(verdict=Verdict.PERMIT)
