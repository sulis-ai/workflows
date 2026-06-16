"""Worker pool port protocol.

ServiceSpec §3: Operations - Worker pool for background execution.
"""

from __future__ import annotations

from typing import Protocol


class WorkerPoolPort(Protocol):
    """Protocol for worker pool implementations.

    Defines the interface for background execution processing.
    """

    @property
    def is_running(self) -> bool:
        """Check if worker pool is currently running."""
        ...

    async def start(self) -> None:
        """Start the worker pool.

        Begins polling for and processing executions.
        """
        ...

    async def stop(self) -> None:
        """Stop the worker pool gracefully.

        Waits for in-progress work to complete before stopping.
        """
        ...

    def get_stats(self) -> dict[str, int | bool]:
        """Get worker pool statistics.

        Returns:
            Dictionary with stats like processed_count, error_count, is_running
        """
        ...
