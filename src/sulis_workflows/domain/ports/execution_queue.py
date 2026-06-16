"""ExecutionQueue port protocol.

ServiceSpec §3: Operations - Queue abstraction for async dispatch
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sulis_workflows.domain.models.execution_state import ExecutionState


class ExecutionQueue(Protocol):
    """Port for execution queue dispatch.

    Enables Ports & Adapters pattern - implementations:
    - MemoryExecutionQueue (testing)
    - CloudRunJobQueue (production)
    """

    async def enqueue(self, execution: ExecutionState) -> None:
        """Enqueue execution for processing.

        Args:
            execution: Execution state to queue for processing
        """
        ...

    async def dequeue(self) -> str | None:
        """Dequeue next execution ID for processing.

        Returns:
            Execution ID if queue not empty, None otherwise
        """
        ...

    async def get_queue_depth(self) -> int:
        """Get current queue depth.

        Returns:
            Number of pending executions in queue
        """
        ...
