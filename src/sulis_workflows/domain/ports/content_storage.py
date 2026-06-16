"""Content storage port — adapter-agnostic file/blob access (TDD §3.3).

Slice-1 surface for the workflow service's file-reading needs. The port
is implemented by:

- ``FilesystemAdapter`` (development / tests) — reads from a local
  workspace root.
- ``GitHubAdapter`` (production) — reads from a GitHub repository via
  the contents API.

Concrete adapters land in WP-MIG-2 / WP-MIG-5. This module defines the
:class:`Protocol` and the request / result value-objects so the
WP-5 ``read_file`` stage primitive can be tested against a fake in-
memory implementation today.

Every adapter MUST extend :class:`IdentifiedAdapter` (the
``AdapterIdentity`` guarantee from WP-ARMOR-01 / ADR-209) and SHOULD
declare its identity at composition-root construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.engine_cache import WorkspacePath
from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "ContentStoragePort",
    "PermanentStorageError",
    "ReadResult",
    "StorageError",
    "StubContentStorageAdapter",
    "TransientStorageError",
]


@dataclass(frozen=True)
class ReadResult:
    """A single file read's bytes + metadata.

    Mirrors the WP-5 ``ReadFileResult`` shape but at the port layer —
    the stage primitive maps this into ``ReadFileResult`` after the
    sandbox / cache / instrumentation chain runs.
    """

    path: WorkspacePath
    content: bytes
    total_lines: int
    more_available: bool
    size_bytes: int
    mtime: datetime | None
    encoding: str


class StorageError(Exception):
    """Base class for storage adapter errors.

    Adapters MUST classify failures into transient vs permanent so the
    primitive's retry policy can act on the correct branch.
    """

    def __init__(self, *, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{message} ({path!r})")


class TransientStorageError(StorageError):
    """Temporary storage failure (network blip, rate limit, throttle).

    The stage primitive retries via the existing ``tenacity`` policy on
    this exception class (NFR-17).
    """


class PermanentStorageError(StorageError):
    """Permanent storage failure (not found, forbidden, malformed path).

    The stage primitive does NOT retry on this exception class; it
    propagates after a single attempt.
    """


@runtime_checkable
class ContentStoragePort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic content-storage protocol.

    Three invariants on every method (per TDD §3.3):

    1. ``platform_id`` is a non-optional keyword argument (NFR-21).
    2. ``run_id`` is a non-optional keyword argument (NFR-11).
    3. Workspace-resolving paths are caller-resolved against the
       sandbox before the adapter sees them. The adapter MUST NOT
       perform its own path-traversal hardening — that is the
       :class:`Sandbox`'s job at the primitive boundary.
    """

    async def read(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ReadResult: ...

    async def mtime(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> float: ...


@dataclass
class StubContentStorageAdapter:
    """In-memory stub for unit-mode contract tests (WP-MIG-6).

    Returns a deterministic single-line file body and a fixed mtime
    so the contract fixture
    (``tests/contracts/content_storage_port_contract.py``) can drive
    shape-only assertions before WP-MIG-5 wires the real GitHub +
    Filesystem adapters behind this port.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubContentStorageAdapter",
            port_name="ContentStoragePort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def read(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ReadResult:
        self.observed_calls.append((platform_id, run_id))
        body = f"stub-content:{path}".encode()
        return ReadResult(
            path=path,
            content=body,
            total_lines=1,
            more_available=False,
            size_bytes=len(body),
            mtime=None,
            encoding="utf-8",
        )

    async def mtime(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> float:
        self.observed_calls.append((platform_id, run_id))
        return 0.0
