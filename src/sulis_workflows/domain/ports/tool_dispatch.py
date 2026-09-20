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
- ``sandbox_root: PathLike`` (NFR-14, non-optional keyword).

The :class:`Sandbox` (WP-7) enforces the path-traversal contract before
the adapter sees a path; the adapter itself MUST NOT re-validate the
sandbox boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.engine_cache import WorkspacePath

#: A path this port accepts or returns.
#:
#: ⚠️ Measured, 2026-09-20: nothing in this library or in any adapter we ship
#: ever constructs a :class:`WorkspacePath` for these calls — the compiler's own
#: step node declares ``sandbox_root: str | None`` and passes a string straight
#: through, and every host adapter does the same. The port declared a
#: value-object contract that no caller has ever honoured, so a typed consumer
#: (a host implementing this port with plain strings, which is all any of them
#: do) failed to satisfy it the moment the package started shipping its
#: annotations. Accepting both is what is actually true; narrowing to the value
#: object would be a breaking change to every adapter, and narrowing to `str`
#: would throw away a distinction the cache still uses.
PathLike = str | WorkspacePath
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

    path: PathLike
    line: int
    column: int
    text: str


@runtime_checkable
class ToolDispatchPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic stage-primitive dispatch protocol.

    The typed workspace trio covers the slice-1 surface:

    - ``read_file`` — batched read (FR-5). Returns a
      :class:`ReadFileResult` with truncation metadata.
    - ``glob`` — sandbox-rooted glob expansion. Returns a list of
      :class:`WorkspacePath`.
    - ``ripgrep`` — structured grep across one or more paths. Returns
      a list of :class:`RipgrepMatch` value-objects.

    ``invoke`` is the generic escape hatch for primitives BEYOND the
    workspace trio (e.g. a ``subprocess`` / ``http_call`` a consumer's
    tool catalogue declares). The engine stays transport-agnostic — it
    names the primitive + args and the adapter decides how to execute
    it, returning a JSON-friendly dict. This is how richer tool
    coverage is added without growing the engine's surface.

    Every method carries ``sandbox_root`` (NFR-14) plus the tenancy
    keys (NFR-11, NFR-21).

    Error contract (v0.9.0+): an adapter SHOULD raise
    ``sulis_workflows.domain.errors.TransientPortError`` for a failure a retry might
    fix and ``PermanentPortError`` for one it won't -- a compiled node's default
    retry policy acts on this distinction, same contract as ``LLMPort``.

    ``invoke``'s ``step_outputs`` (v0.10.0+): the calling run's own accumulated
    ``state["step_outputs"]`` at the moment this primitive dispatches -- the step node
    already holds this (``compiler/nodes/step.py``'s ``step_fn`` receives the full LangGraph
    ``state``), it just wasn't threaded past the tenancy trio before. Optional and additive:
    every existing adapter that ignores it keeps working unchanged. Exists so an adapter that
    itself recurses into another run (e.g. a ``workflow_dispatch``-kind Tool composing a
    sub-workflow) can seed that sub-run from what THIS run has actually produced so far,
    instead of only ever seeing the top-level run's original inputs -- the gap found live: a
    two-level-deep dispatch (a Workflow's own step dispatching a second Workflow) had no way
    to pass its own intermediate output down, only the outermost run's original inputs.
    """

    async def read_file(
        self,
        path: PathLike,
        *,
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
        offset: int = 0,
        limit: int | None = None,
    ) -> ReadFileResult: ...

    async def glob(
        self,
        pattern: str,
        *,
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
    ) -> list[PathLike]: ...

    async def ripgrep(
        self,
        pattern: str,
        paths: list[PathLike],
        *,
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
    ) -> list[RipgrepMatch]: ...

    async def invoke(
        self,
        primitive: str,
        args: dict,
        *,
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
        step_outputs: dict | None = None,
    ) -> dict: ...


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
        path: PathLike,
        *,
        sandbox_root: PathLike,
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
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
    ) -> list[PathLike]:
        self.observed_calls.append((platform_id, run_id))
        return [WorkspacePath(f"stub-glob:{pattern}")]

    async def ripgrep(
        self,
        pattern: str,
        paths: list[PathLike],
        *,
        sandbox_root: PathLike,
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

    async def invoke(
        self,
        primitive: str,
        args: dict,
        *,
        sandbox_root: PathLike,
        platform_id: str,
        run_id: str,
        step_outputs: dict | None = None,
    ) -> dict:
        self.observed_calls.append((platform_id, run_id))
        return {"primitive": primitive, "args": args, "stub": True, "step_outputs": step_outputs}
