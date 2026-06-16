"""Studio registry + Kind resolver — registration and invocation-time integrity (ADR-208).

This package lands two paired controls from ADR-208:

- :class:`StudioRegistry` — registration-time allowlist mapping
  ``apiVersion`` to the curated studio root path on disk. Only Kind YAMLs
  whose ``apiVersion`` resolves to a studio in the registry, AND whose
  filesystem path is inside that studio's root, are permitted to register.
  Closes **MUC-07** (supply-chain attack on Kind YAML at registration).

- :class:`KindResolver` — invocation-time content-hash freeze + drift
  detection. Converts an abstract :class:`KindRef` into a concrete loaded
  Kind, computing a deterministic content hash over the canonical YAML
  form. When the caller passes a :class:`ResolvedAtCreation` snapshot,
  any hash drift since bind-time raises :class:`KindRefDrift`. Closes
  **MUC-10** (kind_ref substitution between bind and invocation).

Audit emission. Every successful registration emits a
:class:`KindRegistrationEvent` to an :class:`StudioAuditSink`, so a
forensic answer is available for every accepted Kind. Refused
registrations (unknown studio, path outside root) raise typed errors and
DO NOT emit a kind_registration event.

Tenancy. The resolver refuses cross-tenant :class:`KindRef` resolution
with :class:`TenancyViolation` — a ``kind_ref`` belonging to a different
``platform_id`` than the caller is not silently re-resolved.

This module sits in the workflow domain core. No SDK imports, no
infrastructure dependencies, no environment reads. Persistence is
deferred — the registry is in-memory; downstream WPs wire it to
Firestore.

See: ADR-208, TDD §4.8.3, WP-ARMOR-03.
"""

from __future__ import annotations

from sulis_workflows.domain.registry.hashing import canonical_kind_hash
from sulis_workflows.domain.registry.kind_resolver import (
    KindLoader,
    KindRef,
    KindRefDrift,
    KindResolver,
    ResolvedAtCreation,
    ResolvedKind,
    TenancyViolation,
    UnknownKindRef,
)
from sulis_workflows.domain.registry.studio_registry import (
    InMemoryStudioAuditSink,
    KindOutsideStudioPath,
    KindRegistrationEvent,
    StudioAuditSink,
    StudioRegistration,
    StudioRegistry,
    UnknownStudio,
)

__all__ = [
    # Studio registry
    "StudioRegistry",
    "StudioRegistration",
    "UnknownStudio",
    "KindOutsideStudioPath",
    "KindRegistrationEvent",
    "StudioAuditSink",
    "InMemoryStudioAuditSink",
    # Kind resolver
    "KindResolver",
    "KindLoader",
    "KindRef",
    "ResolvedKind",
    "ResolvedAtCreation",
    "KindRefDrift",
    "UnknownKindRef",
    "TenancyViolation",
    # Canonical hashing
    "canonical_kind_hash",
]
