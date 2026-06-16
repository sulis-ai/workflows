"""ExecutionHandler - Domain handler for async workflow execution.

ServiceSpec §3: Operations
Implements the core business logic for workflow execution operations.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sulis_workflows.domain.errors import (
    DuplicateExecutionError,
    ExecutionNotApprovableError,
    ExecutionNotCancellableError,
    ExecutionNotFoundError,
    ExecutionNotRestorableError,
    ExecutionNotResumableError,
    TimeoutExceededError,
    WorkflowNotFoundError,
)
from sulis_workflows.domain.models.execution_state import (
    ExecutionState,
    ExecutionStatus,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sulis.shared.events.domain.ports import EventPublisher
    from sulis_workflows.domain.actions import (
        ApproveExecutionAction,
        ArchiveExecutionAction,
        BatchEnqueueAction,
        BatchEnqueueResult,
        CancelExecutionAction,
        DeleteExecutionAction,
        EnqueueWorkflowAction,
        GetExecutionAction,
        HardDeleteExecutionAction,
        ListExecutionsAction,
        RestoreExecutionAction,
        ResumeExecutionAction,
        WaitForCompletionAction,
    )
    from sulis_workflows.domain.ports.execution_queue import ExecutionQueue
    from sulis_workflows.domain.ports.execution_repository import (
        ExecutionRepository,
    )


class ExecutionHandler:
    """Handler for async workflow execution operations.

    Implements ServiceSpec §3 operations:
    - enqueue: Create and queue workflow execution
    - getExecution: Get execution by ID
    - cancel: Cancel pending/running execution
    - listExecutions: List executions with filters
    - waitForCompletion: Wait for execution to complete

    Uses Ports & Adapters pattern for infrastructure abstraction.
    """

    def __init__(
        self,
        repository: ExecutionRepository,
        queue: ExecutionQueue,
        workflow_validator: Callable[[str], bool] | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        """Initialize handler with ports.

        Args:
            repository: Execution state persistence
            queue: Execution dispatch queue
            workflow_validator: Optional function to validate workflow ID exists
            event_publisher: Optional event publisher for domain events
        """
        self.repository = repository
        self.queue = queue
        self.workflow_validator = workflow_validator
        self.event_publisher = event_publisher

    async def _publish_event(
        self,
        event_type: str,
        execution: ExecutionState,
        extra_data: dict | None = None,
    ) -> None:
        """Publish a domain event for an execution state transition.

        No-op when event_publisher is None (backward-compatible).
        Failures are logged but do not block the transition.
        """
        if not self.event_publisher:
            return
        try:
            from pydantic import BaseModel

            class _EventData(BaseModel):
                execution_id: str
                workflow_id: str
                platform_id: str
                organization_id: str | None = None
                status: str

            data = _EventData(
                execution_id=execution.id,
                workflow_id=execution.workflow_id,
                platform_id=execution.platform_id,
                organization_id=execution.organization_id,
                status=execution.status.value,
            )
            if extra_data:
                # Merge extra fields into data dict after serialisation
                pass

            await self.event_publisher.publish(
                event_type=event_type,
                event_data=data,
                aggregate_id=execution.id,
                metadata={"platform_id": execution.platform_id},
            )
        except Exception:
            logger.warning(
                "Failed to publish event %s for execution %s",
                event_type,
                execution.id,
                exc_info=True,
            )

    async def handle_enqueue(
        self,
        action: EnqueueWorkflowAction,
    ) -> ExecutionState:
        """Enqueue workflow for async execution.

        ServiceSpec §3.2: enqueue operation

        Args:
            action: Enqueue action with workflow details

        Returns:
            Created ExecutionState

        Raises:
            WorkflowNotFoundError: If workflow does not exist
            DuplicateExecutionError: If idempotency key exists with different workflow
        """
        # Validate workflow exists
        if self.workflow_validator and not self.workflow_validator(action.workflow_id):
            raise WorkflowNotFoundError(action.workflow_id)

        # Check idempotency
        if action.idempotency_key:
            existing = await self.repository.get_by_idempotency_key(
                platform_id=action.platform_id,
                idempotency_key=action.idempotency_key,
            )
            if existing:
                # Return existing if same workflow (idempotent)
                if existing.workflow_id == action.workflow_id:
                    return existing
                # Raise error if different workflow
                raise DuplicateExecutionError(
                    idempotency_key=action.idempotency_key,
                    existing_execution_id=existing.id,
                )

        # Generate execution ID
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Calculate scheduled_at if delay provided
        scheduled_at = None
        if action.delay:
            scheduled_at = datetime.now(UTC) + action.delay

        # Create execution state
        execution = ExecutionState(
            id=execution_id,
            workflow_id=action.workflow_id,
            platform_id=action.platform_id,
            organization_id=action.organization_id,
            status=ExecutionStatus.pending,
            input_data=action.input_data,
            scheduled_at=scheduled_at,
            idempotency_key=action.idempotency_key,
            callback_url=action.callback_url,
            created_at=datetime.now(UTC),
            created_by=action.created_by or "system",
        )

        # Save to repository
        await self.repository.save(execution)

        # Publish domain event
        await self._publish_event("workflows.execution.created", execution)

        # Enqueue for processing
        await self.queue.enqueue(execution)

        return execution

    async def handle_get_execution(
        self,
        action: GetExecutionAction,
    ) -> ExecutionState:
        """Get execution by ID.

        ServiceSpec §3.3: getExecution operation

        Args:
            action: Get execution action

        Returns:
            ExecutionState if found

        Raises:
            ExecutionNotFoundError: If execution does not exist
        """
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)
        return execution

    async def handle_cancel(
        self,
        action: CancelExecutionAction,
    ) -> ExecutionState:
        """Cancel execution.

        ServiceSpec §3.5: cancel operation

        Args:
            action: Cancel action

        Returns:
            Updated ExecutionState

        Raises:
            ExecutionNotFoundError: If execution does not exist
            ExecutionNotCancellableError: If execution is in terminal state
        """
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        if not execution.can_cancel():
            raise ExecutionNotCancellableError(
                execution_id=action.execution_id,
                current_status=execution.status,
            )

        # Update status to cancelled and set completed_at
        execution.status = ExecutionStatus.cancelled
        execution.completed_at = datetime.now(UTC)

        # Save updated execution
        await self.repository.save(execution)

        # Publish domain event
        await self._publish_event("workflows.execution.cancelled", execution)

        return execution

    async def handle_approve(
        self,
        action: ApproveExecutionAction,
    ) -> ExecutionState:
        """Approve a gate-interrupted execution.

        Validates the execution is in awaiting_approval status,
        records the decision, and re-enqueues for resume.

        Args:
            action: Approve action with execution ID and decision

        Returns:
            Updated ExecutionState

        Raises:
            ExecutionNotFoundError: If execution does not exist
            ExecutionNotApprovableError: If not in awaiting_approval status
        """
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        if execution.status != ExecutionStatus.awaiting_approval:
            raise ExecutionNotApprovableError(
                execution_id=action.execution_id,
                current_status=execution.status,
            )

        # Store gate decision for executor to use on resume
        input_data = execution.input_data or {}
        input_data["_gate_decision"] = action.decision
        execution.input_data = input_data

        # Transition to running for re-execution
        execution.status = ExecutionStatus.running

        # Save updated execution
        await self.repository.save(execution)

        # Re-enqueue for resume
        await self.queue.enqueue(execution)

        return execution

    async def handle_resume(
        self,
        action: ResumeExecutionAction,
    ) -> ExecutionState:
        """Resume an event-suspended execution.

        Finds the execution by correlation key, validates it is in
        awaiting_event status, stores event data, and re-enqueues.

        Args:
            action: Resume action with correlation key and event data

        Returns:
            Updated ExecutionState

        Raises:
            ExecutionNotFoundError: If no execution found for correlation key
            ExecutionNotResumableError: If not in awaiting_event status
        """
        execution = await self.repository.get_by_correlation_key(
            platform_id=action.platform_id,
            correlation_key=action.correlation_key,
        )
        if execution is None:
            raise ExecutionNotFoundError(action.correlation_key)

        if execution.status != ExecutionStatus.awaiting_event:
            raise ExecutionNotResumableError(
                execution_id=execution.id,
                current_status=execution.status,
            )

        # Store event data for the executor to use on resume
        input_data = execution.input_data or {}
        input_data["_event_data"] = action.event_data
        execution.input_data = input_data

        # Transition to running for re-execution
        execution.status = ExecutionStatus.running

        # Save updated execution
        await self.repository.save(execution)

        # Re-enqueue for resume
        await self.queue.enqueue(execution)

        return execution

    async def handle_list_executions(
        self,
        action: ListExecutionsAction,
    ) -> list[ExecutionState]:
        """List executions with optional filters.

        ServiceSpec §3.4: listExecutions operation

        Args:
            action: List action with filters

        Returns:
            List of matching ExecutionState objects
        """
        results = await self.repository.list(
            platform_id=action.platform_id,
            organization_id=action.organization_id,
            workflow_id=action.workflow_id,
            status=action.status,
            limit=action.limit,
            cursor=action.cursor,
        )

        # Filter out deleted unless explicitly requested
        if not action.include_deleted:
            results = [r for r in results if not r.is_deleted]

        return results

    async def handle_delete(
        self,
        action: DeleteExecutionAction,
    ) -> ExecutionState:
        """Soft-delete an execution.

        ServiceSpec §2.5: Soft delete operation

        Args:
            action: Delete action with execution ID

        Returns:
            Updated ExecutionState with is_deleted=True

        Raises:
            ExecutionNotFoundError: If execution does not exist
        """
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        # Mark as deleted
        execution.is_deleted = True
        execution.deleted_at = datetime.now(UTC)

        # Save updated execution
        await self.repository.save(execution)

        return execution

    async def handle_restore(
        self,
        action: RestoreExecutionAction,
    ) -> ExecutionState:
        """Restore a soft-deleted execution.

        ServiceSpec §2.5: Restore operation

        Args:
            action: Restore action with execution ID

        Returns:
            Updated ExecutionState with is_deleted=False

        Raises:
            ExecutionNotFoundError: If execution does not exist
            ExecutionNotRestorableError: If execution is not deleted
        """
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        if not execution.is_deleted:
            raise ExecutionNotRestorableError(action.execution_id)

        # Restore
        execution.is_deleted = False
        execution.deleted_at = None

        # Save updated execution
        await self.repository.save(execution)

        return execution

    async def handle_wait(
        self,
        action: WaitForCompletionAction,
    ) -> ExecutionState:
        """Wait for execution to reach a terminal state.

        ServiceSpec §3.6: waitForCompletion operation

        Polls the repository until execution reaches a terminal state
        (completed, failed, cancelled) or timeout is exceeded.

        Args:
            action: Wait action with execution ID and timeout

        Returns:
            ExecutionState when terminal state reached

        Raises:
            ExecutionNotFoundError: If execution does not exist
            TimeoutExceededError: If timeout exceeded before completion
        """
        # Terminal statuses that signal completion
        terminal_statuses = {
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        }

        # Calculate deadline
        start_time = datetime.now(UTC)
        deadline = start_time + action.timeout
        poll_seconds = action.poll_interval.total_seconds()

        while datetime.now(UTC) < deadline:
            # Get current execution state
            execution = await self.repository.get(action.execution_id)
            if execution is None:
                raise ExecutionNotFoundError(action.execution_id)

            # Check if terminal
            if execution.status in terminal_statuses:
                return execution

            # Wait before next poll
            await asyncio.sleep(poll_seconds)

        # Timeout exceeded
        raise TimeoutExceededError(
            execution_id=action.execution_id,
            timeout_seconds=int(action.timeout.total_seconds()),
        )

    async def handle_archive(
        self,
        action: ArchiveExecutionAction,
    ) -> bool:
        """Archive an execution to archive storage.

        ServiceSpec §2.5: Archive operation

        Args:
            action: Archive action with execution ID

        Returns:
            True if archived successfully

        Raises:
            ExecutionNotFoundError: If execution does not exist
        """
        # Check execution exists first
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        # Archive to archive storage
        result = await self.repository.archive(action.execution_id)
        return result

    async def handle_hard_delete(
        self,
        action: HardDeleteExecutionAction,
    ) -> bool:
        """Permanently delete an execution.

        ServiceSpec §2.5: Hard delete operation

        Args:
            action: Hard delete action with execution ID

        Returns:
            True if deleted successfully

        Raises:
            ExecutionNotFoundError: If execution does not exist
        """
        # Check execution exists first
        execution = await self.repository.get(action.execution_id)
        if execution is None:
            raise ExecutionNotFoundError(action.execution_id)

        # Permanently delete
        result = await self.repository.hard_delete(action.execution_id)
        return result

    async def handle_batch_enqueue(
        self,
        action: BatchEnqueueAction,
    ) -> BatchEnqueueResult:
        """Batch enqueue multiple workflows.

        ServiceSpec §3.9: Batch operations

        Args:
            action: Batch enqueue action with operations list

        Returns:
            BatchEnqueueResult with per-operation results and summary
        """
        from sulis_workflows.domain.actions import BatchEnqueueResult

        results: list[dict] = []
        succeeded = 0
        failed = 0

        for index, operation in enumerate(action.operations):
            try:
                # Process single enqueue
                execution = await self.handle_enqueue(operation)
                results.append(
                    {
                        "index": index,
                        "execution_id": execution.id,
                        "success": True,
                    }
                )
                succeeded += 1

            except Exception as e:
                results.append(
                    {
                        "index": index,
                        "success": False,
                        "error": str(e),
                    }
                )
                failed += 1

                # Stop on error if configured
                if action.stop_on_error:
                    break

        return BatchEnqueueResult(
            results=results,
            summary={
                "total": len(action.operations),
                "succeeded": succeeded,
                "failed": failed,
            },
        )
