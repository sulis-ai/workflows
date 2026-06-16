"""Kind resolver — content-hash freeze + drift detection (ADR-208, WP-ARMOR-03).

The resolver converts an abstract :class:`KindRef` into a concrete
:class:`ResolvedKind`. Two integrity properties hold at this boundary:

- **Drift detection** (closes MUC-10). The caller passes an optional
  :class:`ResolvedAtCreation` snapshot taken at ContentBrief bind time.
  If the current content hash differs from the snapshot's, the resolver
  raises :class:`KindRefDrift` carrying both hashes. Re-binding to the
  new version is an explicit caller action with fresh authz.

- **Tenancy enforcement**. A ``kind_ref`` resolved against a different
  tenant's Kind raises :class:`TenancyViolation`. Same WP-CHAOS-04 test
  surface as the manifest-engine's per-tenant gates.

The :class:`KindLoader` protocol is the boundary that turns a
``(apiVersion, kind, platform_id)`` triple into the actual Kind bytes.
The slice-1 implementation is a filesystem loader (WP-10); this module
defines the contract.

This module is in the workflow domain core — no infrastructure, no SDK
imports, no environment reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from sulis_workflows.domain.registry.hashing import canonical_kind_hash

__all__ = [
    "KindRef",
    "ResolvedAtCreation",
    "ResolvedKind",
    "KindLoader",
    "KindResolver",
    "KindRefDrift",
    "UnknownKindRef",
    "TenancyViolation",
]


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class KindRef:
    """Abstract reference to a Kind by ``(apiVersion, kind)``.

    A KindRef on its own is not enough to invoke a Kind — the engine
    needs the resolved bytes plus the binding ``platform_id``. The
    resolver supplies both via :class:`ResolvedKind`.

    KindRef is the field shape ContentBrief stores (WP-13 wires it on
    the entity).
    """

    api_version: str
    kind: str

    def __post_init__(self) -> None:
        if not self.api_version:
            raise ValueError("api_version must be non-empty")
        if not self.kind:
            raise ValueError("kind must be non-empty")


@dataclass(frozen=True)
class ResolvedAtCreation:
    """Frozen content snapshot taken at ContentBrief bind time.

    Persisted on the ContentBrief alongside ``kind_ref``. At invocation
    time the resolver recomputes the current Kind's content hash and
    compares; mismatch -> :class:`KindRefDrift`.

    Attributes
    ----------
    content_hash:
        64-char lowercase hex SHA-256 over the canonical Kind YAML form
        (see :func:`canonical_kind_hash`).
    metadata_version:
        The Kind YAML's ``metadata.version`` at bind time. Carried for
        operator-facing diagnostics — the hash is the authoritative
        integrity check.
    """

    content_hash: str
    metadata_version: str

    def __post_init__(self) -> None:
        if not _HEX64_RE.match(self.content_hash):
            raise ValueError(
                "content_hash must be 64-char lowercase hex (SHA-256); got "
                f"length={len(self.content_hash)}"
            )
        if not self.metadata_version:
            raise ValueError("metadata_version must be non-empty")


@dataclass(frozen=True)
class ResolvedKind:
    """A KindRef successfully resolved against the loader.

    Carries the bytes the engine will compile + the metadata + the
    computed current content hash. WP-3 (Kind compiler) consumes this.
    """

    api_version: str
    kind: str
    metadata_name: str
    metadata_version: str
    content_hash: str
    yaml_bytes: bytes


# ---------------------------------------------------------------------------
# Loader contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedKindRecord:
    """What a :class:`KindLoader` returns to the resolver.

    Mirrors :class:`ResolvedKind` but carries the binding ``platform_id``
    so the resolver can perform the tenancy check before re-emitting
    the public :class:`ResolvedKind` (which intentionally does not
    expose the binding tenant).
    """

    api_version: str
    kind: str
    metadata_name: str
    metadata_version: str
    platform_id: str
    yaml_bytes: bytes


class KindLoader(Protocol):
    """The boundary the resolver crosses to fetch Kind bytes.

    Slice-1 implementation: filesystem loader walking
    ``methodology/studios/{studio}/kinds/`` (WP-10). Production
    implementation: Firestore-backed lookup over the registered Kinds.

    Contract semantics
    ------------------

    The loader returns the record keyed on ``(kind_ref.api_version,
    kind_ref.kind)`` and surfaces the OWNING ``platform_id`` in the
    returned record — it does NOT filter by ``platform_id``. The
    ``platform_id`` parameter is supplied so loaders can prioritise
    same-tenant records when multiple records exist for the same
    ``(apiVersion, kind)`` (cross-tenant disambiguation); the
    *tenancy check* is the resolver's job, performed on the returned
    record's ``platform_id``.

    Returning ``None`` means 'no such Kind exists for the caller in any
    visible scope' — the resolver translates that into
    :class:`UnknownKindRef`. A record with a different
    ``platform_id`` than the caller's results in
    :class:`TenancyViolation`, not :class:`UnknownKindRef`.

    The duck-typed return matches :class:`LoadedKindRecord` field-shape
    so test stubs can return their own data classes without inheriting.
    """

    def load(self, kind_ref: KindRef, *, platform_id: str) -> LoadedKindRecord | None: ...


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class UnknownKindRef(Exception):
    """Raised when a :class:`KindRef` does not resolve to any loaded Kind.

    Distinguishes "the Kind does not exist" from "the Kind exists on a
    different tenant" — the latter raises :class:`TenancyViolation`.
    """

    def __init__(self, kind_ref: KindRef, *, platform_id: str) -> None:
        super().__init__(
            f"KindRef {kind_ref.api_version}/{kind_ref.kind} not found "
            f"for platform_id={platform_id}"
        )
        self.kind_ref = kind_ref
        self.platform_id = platform_id


class KindRefDrift(Exception):
    """Raised when the current content hash differs from the expected one.

    Both hashes are surfaced so the caller can show the operator exactly
    what changed and offer an explicit re-bind path (which triggers
    fresh ``content.kinds:invoke`` authz on the new content).

    Attributes
    ----------
    kind_ref:
        The KindRef the caller tried to resolve.
    expected_hash:
        The frozen content hash from
        :attr:`ResolvedAtCreation.content_hash`.
    current_hash:
        The freshly computed content hash from the loader's current
        bytes.
    expected_metadata_version:
        ``metadata.version`` at bind time.
    current_metadata_version:
        ``metadata.version`` of the currently-loaded Kind.
    """

    def __init__(
        self,
        *,
        kind_ref: KindRef,
        expected_hash: str,
        current_hash: str,
        expected_metadata_version: str,
        current_metadata_version: str,
    ) -> None:
        super().__init__(
            f"kind_ref_drift on {kind_ref.api_version}/{kind_ref.kind}: "
            f"expected hash {expected_hash[:8]}... "
            f"(version {expected_metadata_version}); "
            f"current hash {current_hash[:8]}... "
            f"(version {current_metadata_version})"
        )
        self.kind_ref = kind_ref
        self.expected_hash = expected_hash
        self.current_hash = current_hash
        self.expected_metadata_version = expected_metadata_version
        self.current_metadata_version = current_metadata_version


class TenancyViolation(Exception):
    """Raised when a KindRef resolves to a Kind on a different tenant.

    The owning ``platform_id`` is held internally but not exposed in
    the public attribute set so cross-tenant identification leaks are
    avoided. The caller's ``platform_id`` is exposed for operator-facing
    routing.
    """

    def __init__(
        self,
        *,
        kind_ref: KindRef,
        caller_platform_id: str,
        owning_platform_id: str,
    ) -> None:
        super().__init__(
            f"kind_ref {kind_ref.api_version}/{kind_ref.kind} is not "
            f"visible to platform_id={caller_platform_id}"
        )
        self.kind_ref = kind_ref
        self.caller_platform_id = caller_platform_id
        # Held privately — operators with access to the audit log can correlate.
        self._owning_platform_id = owning_platform_id


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


class KindResolver:
    """Resolve a :class:`KindRef` to a :class:`ResolvedKind`.

    The resolver does three things:

    1. Loads the Kind via the injected :class:`KindLoader`. Missing
       Kind -> :class:`UnknownKindRef`.
    2. Enforces tenancy: a Kind whose binding ``platform_id`` differs
       from the caller's raises :class:`TenancyViolation`.
    3. Computes the current canonical content hash. If the caller
       passed a :class:`ResolvedAtCreation` snapshot, compares against
       it; mismatch -> :class:`KindRefDrift`.

    The resolver does NOT perform authorization. ``content.kinds:invoke``
    authz lives at the KindHandler boundary (WP-KIND-HANDLER); the
    resolver's role is integrity.
    """

    def __init__(self, *, loader: KindLoader) -> None:
        self._loader = loader

    def resolve(
        self,
        kind_ref: KindRef,
        *,
        platform_id: str,
        expected_at_creation: ResolvedAtCreation | None,
    ) -> ResolvedKind:
        """Resolve a KindRef into the current loaded Kind.

        Parameters
        ----------
        kind_ref:
            The abstract reference.
        platform_id:
            The caller's tenant identifier. Used for the tenancy check.
        expected_at_creation:
            The ContentBrief's frozen snapshot, if a binding existed at
            bind time. ``None`` is the first-bind path — drift detection
            is skipped; the caller takes the freshly computed hash.

        Returns
        -------
        ResolvedKind

        Raises
        ------
        UnknownKindRef
            If the loader returns nothing for ``(kind_ref, platform_id)``
            AND the loader returns nothing for ``(kind_ref, *)`` either.
        TenancyViolation
            If the loader returns a record under a different
            ``platform_id`` than the caller's.
        KindRefDrift
            If ``expected_at_creation`` is provided and the current
            content hash differs.
        """
        record = self._loader.load(kind_ref, platform_id=platform_id)

        if record is None:
            # The loader doesn't have anything for the caller's tenant.
            # Probe the other tenants to distinguish 'truly missing' from
            # 'cross-tenant'. We do NOT iterate platform_ids — the
            # loader is expected to expose that distinction itself if it
            # cares to; for slice 1 we keep things simple and emit
            # UnknownKindRef. WP-CHAOS-04 covers the cross-tenant case
            # via a loader stub that returns the other-tenant record.
            raise UnknownKindRef(kind_ref, platform_id=platform_id)

        if record.platform_id != platform_id:
            raise TenancyViolation(
                kind_ref=kind_ref,
                caller_platform_id=platform_id,
                owning_platform_id=record.platform_id,
            )

        current_hash = canonical_kind_hash(record.yaml_bytes)

        if expected_at_creation is not None:
            if current_hash != expected_at_creation.content_hash:
                raise KindRefDrift(
                    kind_ref=kind_ref,
                    expected_hash=expected_at_creation.content_hash,
                    current_hash=current_hash,
                    expected_metadata_version=(expected_at_creation.metadata_version),
                    current_metadata_version=record.metadata_version,
                )

        return ResolvedKind(
            api_version=record.api_version,
            kind=record.kind,
            metadata_name=record.metadata_name,
            metadata_version=record.metadata_version,
            content_hash=current_hash,
            yaml_bytes=record.yaml_bytes,
        )
