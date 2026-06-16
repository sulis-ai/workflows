"""SchedulerPort protocol for delayed execution scheduling.

ServiceSpec §3: Operations - Scheduler abstraction for delayed execution
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class SchedulerPort(Protocol):
    """Port for scheduling delayed executions.

    Enables Ports & Adapters pattern - implementations:
    - MemoryScheduler (testing)
    - CloudSchedulerAdapter (production)
    """

    async def schedule(
        self,
        execution_id: str,
        scheduled_at: datetime,
        callback_url: str | None = None,
    ) -> str:
        """Schedule an execution for delayed processing.

        Args:
            execution_id: ID of the execution to schedule
            scheduled_at: When the execution should run
            callback_url: Optional URL to call on completion

        Returns:
            Schedule job ID for tracking/cancellation
        """
        ...

    async def cancel(self, job_id: str) -> bool:
        """Cancel a scheduled execution.

        Args:
            job_id: Schedule job ID to cancel

        Returns:
            True if cancelled, False if not found or already executed
        """
        ...

    async def get_scheduled(self, execution_id: str) -> datetime | None:
        """Get scheduled time for an execution.

        Args:
            execution_id: Execution ID to look up

        Returns:
            Scheduled datetime or None if not scheduled
        """
        ...

    async def get_due_executions(self, before: datetime | None = None) -> list[str]:
        """Get execution IDs that are due for processing.

        Args:
            before: Optional cutoff time (defaults to now)

        Returns:
            List of execution IDs that should be processed
        """
        ...
