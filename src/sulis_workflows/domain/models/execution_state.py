"""ExecutionState model for async workflow execution.

ServiceSpec §2: Entities
- ExecutionState entity with sys envelope
- Pydantic aliases for camelCase API responses
- Lifecycle state machine (pending → running → completed/failed/cancelled)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Execution lifecycle states.

    ServiceSpec §2.4: Lifecycle State Machine
    """

    pending = "pending"
    """Execution queued, waiting to start."""

    running = "running"
    """Execution in progress."""

    completed = "completed"
    """Execution finished successfully."""

    failed = "failed"
    """Execution failed with error."""

    cancelled = "cancelled"
    """Execution cancelled by user."""

    awaiting_approval = "awaiting_approval"
    """Execution paused at gate, waiting for approval decision."""

    awaiting_event = "awaiting_event"
    """Execution suspended, waiting for external event callback."""


class ExecutionState(BaseModel):
    """Async workflow execution state.

    ServiceSpec §2.1: Entity Schema
    - ID prefix: exec_
    - Platform-scoped with optional organization
    - Immutable after completion

    ServiceSpec §2.2: Pydantic Aliases
    - All fields use camelCase aliases for API responses
    """

    # Identity fields
    id: str = Field(
        ...,
        alias="id",
        description="Unique execution ID with exec_ prefix",
        json_schema_extra={"x-display": {"order": 1, "label": "Execution ID"}},
    )
    workflow_id: str = Field(
        ...,
        alias="workflowId",
        description="ID of the workflow being executed",
        json_schema_extra={
            "x-display": {"order": 2, "label": "Workflow"},
            "x-enum-source": "workflows/listDefinitions",
        },
    )
    platform_id: str = Field(
        ...,
        alias="platformId",
        description="Platform that owns this execution",
    )
    organization_id: str | None = Field(
        default=None,
        alias="organizationId",
        description="Organization scope (optional for B2C platforms)",
    )

    # State fields
    status: ExecutionStatus = Field(
        default=ExecutionStatus.pending,
        alias="status",
        description="Current execution status",
        json_schema_extra={
            "x-display": {"order": 3, "label": "Status"},
            "x-enum-labels": {
                "pending": "Waiting to Start",
                "running": "Running",
                "completed": "Completed",
                "failed": "Failed",
                "cancelled": "Cancelled",
                "awaiting_approval": "Awaiting Approval",
                "awaiting_event": "Awaiting Event",
            },
        },
    )
    correlation_key: str | None = Field(
        default=None,
        alias="correlationKey",
        description="Domain-specific key for finding suspended executions by external event",
    )
    current_step: str | None = Field(
        default=None,
        alias="currentStep",
        description="Name of the currently executing step",
        json_schema_extra={
            "x-display": {"order": 4, "label": "Current Step"},
            "x-visibility": {"condition": "status == 'running'"},
        },
    )
    progress: float | None = Field(
        default=None,
        alias="progress",
        ge=0.0,
        le=100.0,
        description="Execution progress percentage (0-100)",
        json_schema_extra={
            "x-display": {"order": 5, "label": "Progress"},
            "x-visibility": {"condition": "status == 'running'"},
        },
    )

    # Data fields
    input_data: dict[str, Any] | None = Field(
        default=None,
        alias="inputData",
        description="Input data provided at enqueue time",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        alias="result",
        description="Execution result (on success)",
        json_schema_extra={
            "x-visibility": {"condition": "status == 'completed'"},
        },
    )
    error: dict[str, Any] | None = Field(
        default=None,
        alias="error",
        description="Error details (on failure)",
        json_schema_extra={
            "x-visibility": {"condition": "status == 'failed'"},
        },
    )

    # Scheduling fields
    scheduled_at: datetime | None = Field(
        default=None,
        alias="scheduledAt",
        description="Scheduled start time (for delayed execution)",
    )
    idempotency_key: str | None = Field(
        default=None,
        alias="idempotencyKey",
        description="Client-provided key for idempotent requests",
    )
    callback_url: str | None = Field(
        default=None,
        alias="callbackUrl",
        description="URL to POST completion notification",
    )

    # Timestamp fields (sys envelope)
    created_at: datetime = Field(
        ...,
        alias="createdAt",
        description="When execution was enqueued",
    )
    started_at: datetime | None = Field(
        default=None,
        alias="startedAt",
        description="When execution started running",
    )
    completed_at: datetime | None = Field(
        default=None,
        alias="completedAt",
        description="When execution finished",
    )
    created_by: str = Field(
        ...,
        alias="createdBy",
        description="User or service account that created this execution",
    )

    # Soft delete fields (sys envelope)
    is_deleted: bool = Field(
        default=False,
        alias="isDeleted",
        description="Whether this execution has been soft-deleted",
    )
    deleted_at: datetime | None = Field(
        default=None,
        alias="deletedAt",
        description="When execution was soft-deleted",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "x-field-groups": [
                {
                    "name": "identity",
                    "fields": ["id", "workflowId", "platformId", "organizationId"],
                },
                {"name": "state", "fields": ["status", "currentStep", "progress"]},
                {"name": "data", "fields": ["inputData", "result", "error"]},
                {"name": "scheduling", "fields": ["scheduledAt", "idempotencyKey"]},
                {"name": "callbacks", "fields": ["callbackUrl"]},
                {
                    "name": "timestamps",
                    "fields": ["createdAt", "startedAt", "completedAt", "createdBy"],
                },
            ],
        },
    }

    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.status in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        )

    def can_cancel(self) -> bool:
        """Check if execution can be cancelled."""
        return self.status in (
            ExecutionStatus.pending,
            ExecutionStatus.running,
            ExecutionStatus.awaiting_approval,
            ExecutionStatus.awaiting_event,
        )
