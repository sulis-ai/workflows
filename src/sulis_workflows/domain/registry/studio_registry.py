"""Studio registry — the registration-time allowlist (ADR-208, WP-ARMOR-03).

A :class:`StudioRegistry` is the curated mapping of ``apiVersion`` to a
studio root path on disk. Kind YAML registration consults the registry
twice:

1. ``resolve_studio(api_version)`` — refuse if the apiVersion isn't in
   the registry (typed :class:`UnknownStudio` error).
2. ``is_path_in_studio(yaml_path, api_version)`` — refuse if the YAML's
   path is not inside the studio's declared root (typed
   :class:`KindOutsideStudioPath` error).

The :meth:`StudioRegistry.assert_registration_allowed` convenience
gathers both checks under one call and emits the
:class:`KindRegistrationEvent` audit on success.

Path comparison is purely lexical (``PurePosixPath`` containment), with
``..`` segments resolved before comparison. Symlink-following is not the
registry's concern — that lives at the filesystem-adapter layer when
the registration path is wired (WP-10).

This module is in the workflow domain core. Persistence, distribution,
and registry-update workflows are downstream concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Protocol

__all__ = [
    "StudioRegistration",
    "StudioRegistry",
    "UnknownStudio",
    "KindOutsideStudioPath",
    "KindRegistrationEvent",
    "StudioAuditSink",
    "InMemoryStudioAuditSink",
]


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudioRegistration:
    """One binding in the registry: apiVersion -> studio root.

    Attributes
    ----------
    api_version:
        The Kind YAML's ``apiVersion`` field — e.g.
        ``"product-development/v1alpha1"``.
    studio_root:
        Repository-relative path to the studio bundle's root — e.g.
        ``PurePosixPath("methodology/studios/product-development")``.
        Kind YAML files whose path is inside this root are permitted to
        register under this apiVersion.
    registered_at:
        Wall-clock time the binding was added to the registry. UTC.
    registered_by:
        Principal who added the binding. Provenance for audit.
    """

    api_version: str
    studio_root: PurePosixPath
    registered_at: datetime
    registered_by: str

    def __post_init__(self) -> None:
        if not self.api_version:
            raise ValueError("api_version must be non-empty")
        if str(self.studio_root) in ("", "."):
            raise ValueError("studio_root must be non-empty")
        if not self.registered_by:
            raise ValueError("registered_by must be non-empty")


@dataclass(frozen=True)
class KindRegistrationEvent:
    """Audit record emitted on every accepted Kind registration.

    Carries the full provenance set per ADR-208: ``{api_version, kind,
    metadata.name, metadata.version, principal_id, content_hash,
    yaml_path}``. Operators correlate these with their issue tracker /
    methodology-change PRs to attribute every Kind in the registry.

    The downstream observability adapter serialises these to PubSub when
    the audit sink is wired to the observability port.
    """

    api_version: str
    kind: str
    metadata_name: str
    metadata_version: str
    principal_id: str
    content_hash: str
    yaml_path: PurePosixPath


# ---------------------------------------------------------------------------
# Audit sink contract + in-memory implementation
# ---------------------------------------------------------------------------


class StudioAuditSink(Protocol):
    """Sink for :class:`KindRegistrationEvent`.

    Implementations MUST be fire-and-forget at the boundary — they MUST
    NOT raise on emit failure. The registration path has already
    committed the binding; an audit-emit failure must not roll that back.
    """

    def emit(self, event: KindRegistrationEvent) -> None: ...


class InMemoryStudioAuditSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production sinks publish to
    the observability port (wired by WP-8 / WP-10).
    """

    def __init__(self) -> None:
        self._events: list[KindRegistrationEvent] = []

    def emit(self, event: KindRegistrationEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[KindRegistrationEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class UnknownStudio(Exception):
    """Raised when an ``apiVersion`` is not in the studio registry.

    The :attr:`api_version` attribute carries the offending value so the
    caller can audit the rejection and surface it to the operator with
    the same string the YAML claimed.
    """

    def __init__(self, api_version: str) -> None:
        super().__init__(f"apiVersion '{api_version}' is not a registered studio")
        self.api_version = api_version


class KindOutsideStudioPath(Exception):
    """Raised when a Kind YAML's path is not inside its studio's root.

    Attributes
    ----------
    api_version:
        The studio the YAML claimed to belong to.
    yaml_path:
        The on-disk path that failed the containment check.
    studio_root:
        The root the registry has on file for the claimed apiVersion.
    """

    def __init__(
        self,
        *,
        api_version: str,
        yaml_path: PurePosixPath,
        studio_root: PurePosixPath,
    ) -> None:
        super().__init__(
            f"Kind YAML at '{yaml_path}' is outside studio root "
            f"'{studio_root}' for apiVersion '{api_version}'"
        )
        self.api_version = api_version
        self.yaml_path = yaml_path
        self.studio_root = studio_root


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class StudioRegistry:
    """In-memory allowlist of ``(apiVersion -> studio_root)`` bindings.

    Use :meth:`add` and :meth:`unregister` to mutate the registry.

    Use :meth:`resolve_studio` to look up an apiVersion (raises
    :class:`UnknownStudio` on miss).

    Use :meth:`is_path_in_studio` to check whether a given YAML path
    lives inside the studio root for the given apiVersion (returns
    bool; raises :class:`UnknownStudio` if the apiVersion is unknown).

    Use :meth:`assert_registration_allowed` to gate a Kind registration
    end-to-end: both the apiVersion check and the path check run, the
    registration is approved or refused with a typed error, and on
    success a :class:`KindRegistrationEvent` is emitted.

    The registry is not goroutine / thread-safe for concurrent mutation
    while resolutions are in flight; the workflow service runs as a
    single asyncio loop and resolutions take no I/O, so this is fine
    for slice 1.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, StudioRegistration] = {}

    # ----- mutation -----

    def add(self, registration: StudioRegistration) -> None:
        """Insert or replace a binding for ``registration.api_version``."""
        self._bindings[registration.api_version] = registration

    def unregister(self, api_version: str) -> None:
        """Remove a binding. No-op if the apiVersion isn't present."""
        self._bindings.pop(api_version, None)

    # ----- queries -----

    def resolve_studio(self, api_version: str) -> StudioRegistration:
        """Return the binding for ``api_version`` or raise UnknownStudio."""
        try:
            return self._bindings[api_version]
        except KeyError as exc:
            raise UnknownStudio(api_version) from exc

    def is_path_in_studio(self, yaml_path: PurePosixPath, *, api_version: str) -> bool:
        """Return True if ``yaml_path`` is inside the studio's root.

        ``..`` segments are normalised before comparison so a path
        like ``methodology/studios/product-development/../sneaky.yaml``
        is correctly seen as outside the root.

        Raises
        ------
        UnknownStudio
            If ``api_version`` is not in the registry.
        """
        registration = self.resolve_studio(api_version)
        return _path_contains(registration.studio_root, yaml_path)

    # ----- combined gate -----

    def assert_registration_allowed(
        self,
        *,
        api_version: str,
        kind: str,
        metadata_name: str,
        metadata_version: str,
        yaml_path: PurePosixPath,
        principal_id: str,
        content_hash: str,
        audit_sink: StudioAuditSink,
    ) -> StudioRegistration:
        """Approve a Kind registration end-to-end.

        Runs the apiVersion lookup, then the path-containment check. On
        success emits a :class:`KindRegistrationEvent` to ``audit_sink``
        and returns the resolved :class:`StudioRegistration` for the
        caller's records. On failure raises the typed error WITHOUT
        emitting an audit event — refused registrations are not
        forensically interesting in the same channel as accepted ones.

        Raises
        ------
        UnknownStudio
            If ``api_version`` is not registered.
        KindOutsideStudioPath
            If ``yaml_path`` is outside the studio's root.
        """
        registration = self.resolve_studio(api_version)
        if not _path_contains(registration.studio_root, yaml_path):
            raise KindOutsideStudioPath(
                api_version=api_version,
                yaml_path=yaml_path,
                studio_root=registration.studio_root,
            )

        audit_sink.emit(
            KindRegistrationEvent(
                api_version=api_version,
                kind=kind,
                metadata_name=metadata_name,
                metadata_version=metadata_version,
                principal_id=principal_id,
                content_hash=content_hash,
                yaml_path=yaml_path,
            )
        )
        return registration


# ---------------------------------------------------------------------------
# Path containment
# ---------------------------------------------------------------------------


def _path_contains(root: PurePosixPath, candidate: PurePosixPath) -> bool:
    """Return True if ``candidate`` is inside ``root`` after normalising ``..``.

    Lexical containment only — no filesystem access, no symlink resolution.
    The registration path's symlink defence lives at the filesystem-adapter
    boundary (see sandbox primitives in TDD §4.2).
    """
    root_parts = _normalise(root)
    candidate_parts = _normalise(candidate)
    if len(candidate_parts) < len(root_parts):
        return False
    return candidate_parts[: len(root_parts)] == root_parts


def _normalise(path: PurePosixPath) -> tuple[str, ...]:
    """Resolve ``.`` and ``..`` segments lexically, return the normalised parts."""
    out: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if out:
                out.pop()
            # An attempt to walk above the root yields an empty stack —
            # the resulting path is treated as outside any non-empty root.
            continue
        out.append(part)
    return tuple(out)
