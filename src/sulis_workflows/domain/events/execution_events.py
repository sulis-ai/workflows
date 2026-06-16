"""Execution event models for CloudEvents publication.

ServiceSpec §8: Events
- workflows.execution.created: Execution enqueued
- workflows.execution.started: Execution started running
- workflows.execution.completed: Execution completed successfully
- workflows.execution.failed: Execution failed with error
- workflows.execution.cancelled: Execution was cancelled
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from sulis_workflows.domain.models.execution_state import ExecutionStatus


class ExecutionEventBase(BaseModel):
    """Base class for execution events.

    All execution events share common fields for identification
    and tracking within the platform hierarchy.
    """

    execution_id: str = Field(
        ...,
        alias="executionId",
        description="ID of the execution",
    )
    workflow_id: str = Field(
        ...,
        alias="workflowId",
        description="ID of the workflow being executed",
    )
    platform_id: str = Field(
        ...,
        alias="platformId",
        description="Platform that owns this execution",
    )
    organization_id: str | None = Field(
        default=None,
        alias="organizationId",
        description="Organization scope (optional for B2C)",
    )

    model_config = {"populate_by_name": True}


class ExecutionCreatedEvent(ExecutionEventBase):
    """Event published when a workflow execution is created/enqueued.

    ServiceSpec §8.1: workflows.execution.created

    Published when handle_enqueue successfully creates a new execution.
    """

    event_type: ClassVar[str] = "workflows.execution.created"

    idempotency_key: str | None = Field(
        default=None,
        alias="idempotencyKey",
        description="Client-provided idempotency key",
    )
    created_by: str | None = Field(
        default=None,
        alias="createdBy",
        description="User or service that created this execution",
    )


class ExecutionStartedEvent(ExecutionEventBase):
    """Event published when a workflow execution starts running.

    ServiceSpec §8.2: workflows.execution.started

    Published when the executor begins processing the workflow.
    """

    event_type: ClassVar[str] = "workflows.execution.started"


class ExecutionCompletedEvent(ExecutionEventBase):
    """Event published when a workflow execution completes successfully.

    ServiceSpec §8.3: workflows.execution.completed

    Published when the workflow finishes all steps without error.
    """

    event_type: ClassVar[str] = "workflows.execution.completed"

    result: dict[str, Any] | None = Field(
        default=None,
        description="Workflow execution result",
    )


class ExecutionFailedEvent(ExecutionEventBase):
    """Event published when a workflow execution fails.

    ServiceSpec §8.4: workflows.execution.failed

    Published when the workflow fails due to step error or exception.
    """

    event_type: ClassVar[str] = "workflows.execution.failed"

    error_code: str = Field(
        ...,
        alias="errorCode",
        description="Error code (e.g., STEP_FAILED)",
    )
    error_message: str = Field(
        ...,
        alias="errorMessage",
        description="Human-readable error description",
    )


class ExecutionCancelledEvent(ExecutionEventBase):
    """Event published when a workflow execution is cancelled.

    ServiceSpec §8.5: workflows.execution.cancelled

    Published when a user or system cancels a pending/running execution.
    """

    event_type: ClassVar[str] = "workflows.execution.cancelled"

    previous_status: ExecutionStatus | None = Field(
        default=None,
        alias="previousStatus",
        description="Status before cancellation",
    )
    cancelled_by: str | None = Field(
        default=None,
        alias="cancelledBy",
        description="User or service that cancelled the execution",
    )
