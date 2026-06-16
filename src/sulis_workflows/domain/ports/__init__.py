"""Port protocols for infrastructure abstraction.

Ports define interfaces that infrastructure adapters must implement.
This enables the Ports & Adapters pattern for testability.

The slice-1 surface (WP-MIG-6) declares six workflow-domain ports:

- :class:`LLMPort` — adapter-agnostic LLM interface (Anthropic + Claude Code).
- :class:`ToolDispatchPort` — engine stage primitives (read_file / glob /
  ripgrep).
- :class:`ContentStoragePort` — GitHub + Filesystem read / mtime surface.
- :class:`ExecutionRuntimePort` — Cloud Run + CLI job submission.
- :class:`CheckpointingPort` — LangGraph checkpoint persistence.
- :class:`ObservabilityPort` — fire-and-forget instrumentation channel.

The execution-queue, execution-repository, scheduler, and worker-pool
ports were declared by earlier WPs and remain co-located here — they
serve the same hexagonal-architecture role.
"""

from sulis_workflows.domain.ports.base import IdentifiedAdapter
from sulis_workflows.domain.ports.checkpointing import (
    CheckpointHandle,
    CheckpointingPort,
    CheckpointPayload,
    StubCheckpointingAdapter,
    UnknownCheckpoint,
)
from sulis_workflows.domain.ports.content_storage import (
    ContentStoragePort,
    PermanentStorageError,
    ReadResult,
    StorageError,
    StubContentStorageAdapter,
    TransientStorageError,
)
from sulis_workflows.domain.ports.execution_queue import ExecutionQueue
from sulis_workflows.domain.ports.execution_repository import ExecutionRepository
from sulis_workflows.domain.ports.execution_runtime import (
    LEGAL_TERMINAL_STATUSES,
    ExecutionRuntimePort,
    JobHandle,
    JobOutcome,
    JobSpec,
    StubExecutionRuntimeAdapter,
)
from sulis_workflows.domain.ports.llm import (
    LLMPort,
    LLMRequest,
    LLMResponse,
    LLMStreamChunk,
    StubLLMAdapter,
)
from sulis_workflows.domain.ports.observability import (
    OBSERVABILITY_EVENT_CLASSES,
    InMemoryObservabilityRecorder,
    ObservabilityEvent,
    ObservabilityPort,
    ObservabilityRecord,
    stage_lifecycle,
    with_child_run_id,
)
from sulis_workflows.domain.ports.scheduler_port import SchedulerPort
from sulis_workflows.domain.ports.tool_dispatch import (
    ReadFileResult,
    RipgrepMatch,
    StubToolDispatchAdapter,
    ToolDispatchPort,
)
from sulis_workflows.domain.ports.worker_pool_port import WorkerPoolPort

__all__ = [
    "LEGAL_TERMINAL_STATUSES",
    "OBSERVABILITY_EVENT_CLASSES",
    "CheckpointHandle",
    "CheckpointPayload",
    "CheckpointingPort",
    "ContentStoragePort",
    "ExecutionQueue",
    "ExecutionRepository",
    "ExecutionRuntimePort",
    "IdentifiedAdapter",
    "InMemoryObservabilityRecorder",
    "JobHandle",
    "JobOutcome",
    "JobSpec",
    "LLMPort",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "ObservabilityEvent",
    "ObservabilityPort",
    "ObservabilityRecord",
    "PermanentStorageError",
    "ReadFileResult",
    "ReadResult",
    "RipgrepMatch",
    "SchedulerPort",
    "StorageError",
    "StubCheckpointingAdapter",
    "StubContentStorageAdapter",
    "StubExecutionRuntimeAdapter",
    "StubLLMAdapter",
    "StubToolDispatchAdapter",
    "ToolDispatchPort",
    "TransientStorageError",
    "UnknownCheckpoint",
    "WorkerPoolPort",
    "stage_lifecycle",
    "with_child_run_id",
]
