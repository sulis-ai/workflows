"""ExecutionRuntimePort — workflow-domain abstraction over the runtime
that executes a compiled outcome graph (WP-MIG-6).

Adapters (per TDD §3.1):

- ``CloudRunAdapter`` (production seed). Lives today at
  ``shared/workflows/jobs/graph_executor.py``. WP-MIG-3 captures the
  contract that seed satisfies.
- ``CLIRuntimeAdapter`` (development / local). Migrates from
  ``tasks/cli/`` via WP-MIG-3.

The :class:`StubExecutionRuntimeAdapter` here is the in-memory double
that ships green today so the contract fixture
(``tests/contracts/execution_runtime_port_contract.py``) can run.

Per TDD §3.3 every method carries ``platform_id`` + ``run_id`` as
non-optional keyword arguments.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "ExecutionRuntimePort",
    "JobHandle",
    "JobOutcome",
    "JobSpec",
    "LEGAL_TERMINAL_STATUSES",
    "StubExecutionRuntimeAdapter",
]


# Authoritative set of terminal statuses an execution-runtime adapter
# may return. Mirrors FR-9's terminal-state taxonomy at the runtime
# layer: ``succeeded`` for clean completion, ``failed`` for a
# non-retriable failure, ``timed_out`` for the bounded-wait path.
# Adapters that need finer-grained taxonomy declare their own enum
# inside the adapter package; the port narrows back to these three.
LEGAL_TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "timed_out"})


@dataclass(frozen=True)
class JobSpec:
    """The runtime-agnostic job description.

    Adapters map this onto their concrete shape (Cloud Run Job spec,
    CLI argv) at the adapter boundary.
    """

    image: str
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    cpu_millis: int = 1000
    memory_mib: int = 512


@dataclass(frozen=True)
class JobHandle:
    """Opaque handle returned from ``submit_job``.

    Carried by the workflow service across the submit → await boundary.
    The ``job_id`` field is the adapter-specific identifier (Cloud Run
    execution ID, CLI PID, stub UUID); callers MUST treat it as opaque.
    """

    job_id: str


@dataclass(frozen=True)
class JobOutcome:
    """Terminal outcome of an awaited job.

    ``status`` is one of :data:`LEGAL_TERMINAL_STATUSES`. ``exit_code``
    surfaces the adapter's view of the underlying process exit (Cloud
    Run job container exit code, CLI subprocess returncode). ``stdout``
    is the captured tail (last 64 KiB by adapter convention) — included
    so the contract test can verify byte-shape without needing a live
    streaming channel.
    """

    status: str
    exit_code: int
    stdout: str = ""


@runtime_checkable
class ExecutionRuntimePort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic execution-runtime protocol.

    Two call shapes:

    - ``submit_job`` — start a job; return a :class:`JobHandle`.
    - ``await_completion`` — bounded wait; return a :class:`JobOutcome`.

    Per TDD §3.3 every method carries the tenancy keys.
    """

    async def submit_job(
        self,
        spec: JobSpec,
        *,
        platform_id: str,
        run_id: str,
    ) -> JobHandle: ...

    async def await_completion(
        self,
        handle: JobHandle,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> JobOutcome: ...


@dataclass
class StubExecutionRuntimeAdapter:
    """In-memory stub adapter for unit-mode contract tests.

    Records every submission, returns a fresh UUID-based handle, and
    completes synchronously with status ``succeeded``. The production
    adapters (Cloud Run, CLI) implement the same protocol with real
    runtime semantics.
    """

    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubExecutionRuntimeAdapter",
            port_name="ExecutionRuntimePort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def submit_job(
        self,
        spec: JobSpec,
        *,
        platform_id: str,
        run_id: str,
    ) -> JobHandle:
        self.observed_calls.append((platform_id, run_id))
        return JobHandle(job_id=f"stub-{uuid.uuid4().hex[:8]}")

    async def await_completion(
        self,
        handle: JobHandle,
        *,
        platform_id: str,
        run_id: str,
        timeout_s: float,
    ) -> JobOutcome:
        self.observed_calls.append((platform_id, run_id))
        return JobOutcome(status="succeeded", exit_code=0, stdout="stub-ok")
