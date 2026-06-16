"""ExecutionRepository port protocol.

ServiceSpec §2: Entities - Persistence abstraction
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from sulis_workflows.domain.models.execution_state import (
        ExecutionState,
        ExecutionStatus,
    )


class ExecutionRepository(Protocol):
    """Port for execution state persistence.

    Enables Ports & Adapters pattern - implementations:
    - MemoryExecutionRepository (testing)
    - FirestoreExecutionRepository (production)
    """

    async def save(self, execution: ExecutionState) -> None:
        """Save or update execution state.

        Args:
            execution: Execution state to persist
        """
        ...

    async def get(self, execution_id: str) -> ExecutionState | None:
        """Get execution by ID.

        Args:
            execution_id: ID of execution to retrieve

        Returns:
            ExecutionState if found, None otherwise
        """
        ...

    async def get_by_idempotency_key(
        self,
        platform_id: str,
        idempotency_key: str,
    ) -> ExecutionState | None:
        """Get execution by idempotency key.

        Args:
            platform_id: Platform scope
            idempotency_key: Client-provided idempotency key

        Returns:
            ExecutionState if found, None otherwise
        """
        ...

    async def list(
        self,
        platform_id: str,
        organization_id: str | None = None,
        workflow_id: str | None = None,
        status: ExecutionStatus | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[ExecutionState]:
        """List executions with optional filters.

        Args:
            platform_id: Platform scope (required)
            organization_id: Filter by organization
            workflow_id: Filter by workflow
            status: Filter by status
            limit: Maximum results
            cursor: Pagination cursor

        Returns:
            List of matching executions
        """
        ...

    async def get_by_correlation_key(
        self,
        platform_id: str,
        correlation_key: str,
        status: ExecutionStatus | None = None,
    ) -> ExecutionState | None:
        """Get execution by correlation key.

        Args:
            platform_id: Platform scope
            correlation_key: Domain-specific correlation key
            status: Optional status filter

        Returns:
            ExecutionState if found, None otherwise
        """
        ...

    async def update_status(
        self,
        execution_id: str,
        status: ExecutionStatus,
    ) -> ExecutionState | None:
        """Update execution status.

        Args:
            execution_id: ID of execution to update
            status: New status

        Returns:
            Updated ExecutionState if found, None otherwise
        """
        ...

    async def archive(self, execution_id: str) -> bool:
        """Archive execution to archive storage.

        Args:
            execution_id: ID of execution to archive

        Returns:
            True if archived, False if not found
        """
        ...

    async def hard_delete(self, execution_id: str) -> bool:
        """Permanently delete execution.

        Args:
            execution_id: ID of execution to delete

        Returns:
            True if deleted, False if not found
        """
        ...

    async def count_since(self, since: datetime) -> int:
        """Count all executions created since a timestamp (cross-platform).

        Args:
            since: Count executions created at or after this time

        Returns:
            Number of matching executions
        """
        ...
