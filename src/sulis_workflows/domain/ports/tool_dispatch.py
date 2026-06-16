"""ToolDispatchPort — workflow-domain abstraction over the engine's
stage primitives (read_file / glob / ripgrep) — WP-MIG-6.

The four-stage Kind execution path (find / generate / evaluate / decide)
talks to this port whenever a stage needs to inspect a workspace path.
Concrete adapters (WP-5 batched read, WP-6 glob + ripgrep) ship behind
this port; WP-MIG-1 relocates them from ``tasks/`` to
``apps/api/sulis/shared/workflows/infrastructure/stage_primitives/``.

The :class:`StubToolDispatchAdapter` in this module is the in-memory
double for unit-mode contract tests.

Per TDD §3.3 every method carries:

- ``platform_id: str`` (NFR-21, non-optional keyword).
- ``run_id: str`` (NFR-11, non-optional keyword).
- ``sandbox_root: WorkspacePath`` (NFR-14, non-optional keyword).

The :class:`Sandbox` (WP-7) enforces the path-traversal contract before
the adapter sees a path; the adapter itself MUST NOT re-validate the
sandbox boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.engine_cache import WorkspacePath
from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "ReadFileResult",
    "RipgrepMatch",
    "StubToolDispatchAdapter",
    "ToolDispatchPort",
]


@dataclass(frozen=True)
class ReadFileResult:
    """Batched read result from ``ToolDispatchPort.read_file`` (FR-5).

    Carries the file contents AND the ``total_lines`` + ``more_available``
    fields so the caller (the four-stage execution path) can detect a
    truncated read and request the next batch without re-reading from
    byte zero.
    """

    content: str
    total_lines: int
    more_available: bool


@dataclass(frozen=True)
class RipgrepMatch:
    """One structured ``ripgrep`` hit (WP-6 / FR-5).

    The ripgrep adapter returns ``(path, line, column, text)`` per hit
    — not raw stdout. Stage code asserts on these fields, not on
    string fragments.
    """

    path: WorkspacePath
    line: int
    column: int
    text: str


@runtime_checkable
class ToolDispatchPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic stage-primitive dispatch protocol.

    Three methods cover the slice-1 surface:

    - ``read_file`` — batched read (FR-5). Returns a
      :class:`ReadFileResult` with truncation metadata.
    - ``glob`` — sandbox-rooted glob expansion. Returns a list of
      :class:`WorkspacePath`.
    - ``ripgrep`` — structured grep across one or more paths. Returns
      a list of :class:`RipgrepMatch` value-objects.

    Every method carries ``sandbox_root`` (NFR-14) plus the tenancy
    keys (NFR-11, NFR-21).
    """

    async def read_file(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ReadFileResult: ...

    async def glob(
        self,
        pattern: str,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> list[WorkspacePath]: ...

    async def ripgrep(
        self,
        pattern: str,
        paths: list[WorkspacePath],
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> list[RipgrepMatch]: ...


@dataclass
class StubToolDispatchAdapter:
    """In-memory stub for unit-mode contract tests.

    Returns deterministic results so the contract fixture
    (``tests/contracts/tool_dispatch_port_contract.py``) can drive
    shape-only assertions. The production adapter (workflow-service
    stage primitives — WP-MIG-1) implements the same protocol with
    real file / shell behaviour.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubToolDispatchAdapter",
            port_name="ToolDispatchPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def read_file(
        self,
        path: WorkspacePath,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ReadFileResult:
        self.observed_calls.append((platform_id, run_id))
        body = f"stub-read:{path}"
        return ReadFileResult(
            content=body,
            total_lines=body.count("\n") + 1,
            more_available=False,
        )

    async def glob(
        self,
        pattern: str,
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> list[WorkspacePath]:
        self.observed_calls.append((platform_id, run_id))
        return [WorkspacePath(f"stub-glob:{pattern}")]

    async def ripgrep(
        self,
        pattern: str,
        paths: list[WorkspacePath],
        *,
        sandbox_root: WorkspacePath,
        platform_id: str,
        run_id: str,
    ) -> list[RipgrepMatch]:
        self.observed_calls.append((platform_id, run_id))
        return [
            RipgrepMatch(
                path=p,
                line=1,
                column=0,
                text=f"stub-hit:{pattern}",
            )
            for p in paths
        ]
