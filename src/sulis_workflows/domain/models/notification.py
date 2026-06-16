"""Notification models for workflow events.

ServiceSpec §9: Notification triggers for execution events.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    """Types of notifications for execution events."""

    execution_failed = "execution.failed"
    execution_completed = "execution.completed"
    execution_stuck = "execution.stuck"


class NotificationChannel(str, Enum):
    """Channels for delivering notifications."""

    in_app = "in_app"
    email = "email"
    webhook = "webhook"


class NotificationRecipient(str, Enum):
    """Recipient types for notifications."""

    creator = "creator"
    workflows_admin = "workflows_admin"
    subscriber = "subscriber"


# Default channels and recipients per notification type
_NOTIFICATION_DEFAULTS: dict[NotificationType, dict[str, list]] = {
    NotificationType.execution_failed: {
        "channels": [NotificationChannel.in_app, NotificationChannel.email],
        "recipients": [
            NotificationRecipient.creator,
            NotificationRecipient.workflows_admin,
        ],
    },
    NotificationType.execution_completed: {
        "channels": [NotificationChannel.in_app],
        "recipients": [NotificationRecipient.subscriber],
    },
    NotificationType.execution_stuck: {
        "channels": [NotificationChannel.in_app, NotificationChannel.email],
        "recipients": [
            NotificationRecipient.creator,
            NotificationRecipient.workflows_admin,
        ],
    },
}


class NotificationEvent(BaseModel):
    """Event that triggers a notification.

    Created when execution state changes warrant notification.
    """

    type: NotificationType = Field(
        ...,
        description="Type of notification event",
    )

    execution_id: str = Field(
        ...,
        description="ID of the execution",
    )

    platform_id: str = Field(
        ...,
        description="Platform context",
    )

    workflow_id: str = Field(
        ...,
        description="Workflow that was executed",
    )

    created_by: str = Field(
        ...,
        description="User who created the execution",
    )

    error: str | None = Field(
        default=None,
        description="Error message for failed executions",
    )

    stuck_duration: timedelta | None = Field(
        default=None,
        description="How long execution has been stuck",
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the event occurred",
    )

    channels: list[NotificationChannel] | None = Field(
        default=None,
        description="Channels to send notification through",
    )

    recipients: list[NotificationRecipient] | None = Field(
        default=None,
        description="Recipients for the notification",
    )

    def __init__(self, **data: Any) -> None:
        """Initialize with defaults based on notification type."""
        super().__init__(**data)

        # Apply defaults if not provided
        if self.channels is None:
            self.channels = _NOTIFICATION_DEFAULTS[self.type]["channels"]
        if self.recipients is None:
            self.recipients = _NOTIFICATION_DEFAULTS[self.type]["recipients"]


class NotificationTemplate(BaseModel):
    """Template for notification content.

    Templates use {variable} placeholders for dynamic content.
    """

    type: NotificationType = Field(
        ...,
        description="Notification type this template is for",
    )

    channel: NotificationChannel = Field(
        ...,
        description="Channel this template is for",
    )

    subject: str = Field(
        ...,
        description="Subject line template (for email/in_app)",
    )

    body: str = Field(
        ...,
        description="Body content template",
    )

    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Additional metadata (priority, category, etc.)",
    )

    def render_subject(self, context: dict[str, str]) -> str:
        """Render subject with context variables.

        Args:
            context: Dictionary of variable values

        Returns:
            Rendered subject string
        """
        result = self.subject
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    def render_body(self, context: dict[str, str]) -> str:
        """Render body with context variables.

        Args:
            context: Dictionary of variable values

        Returns:
            Rendered body string
        """
        result = self.body
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", value)
        return result


# Pre-defined templates for common notifications
DEFAULT_TEMPLATES: list[NotificationTemplate] = [
    # execution.failed templates
    NotificationTemplate(
        type=NotificationType.execution_failed,
        channel=NotificationChannel.email,
        subject="Workflow Execution Failed: {workflow_id}",
        body="""Your workflow execution has failed.

Execution ID: {execution_id}
Workflow: {workflow_id}
Error: {error}

Please review the execution details in the dashboard.""",
        metadata={"priority": "high"},
    ),
    NotificationTemplate(
        type=NotificationType.execution_failed,
        channel=NotificationChannel.in_app,
        subject="Execution Failed",
        body="Execution {execution_id} failed: {error}",
        metadata={"category": "alert"},
    ),
    # execution.completed templates
    NotificationTemplate(
        type=NotificationType.execution_completed,
        channel=NotificationChannel.in_app,
        subject="Execution Completed",
        body="Your workflow execution {execution_id} has completed successfully.",
        metadata={"category": "info"},
    ),
    # execution.stuck templates
    NotificationTemplate(
        type=NotificationType.execution_stuck,
        channel=NotificationChannel.email,
        subject="Workflow Execution Stuck: {workflow_id}",
        body="""A workflow execution appears to be stuck.

Execution ID: {execution_id}
Workflow: {workflow_id}
Running for: {duration}

Please investigate the execution in the dashboard.""",
        metadata={"priority": "high"},
    ),
    NotificationTemplate(
        type=NotificationType.execution_stuck,
        channel=NotificationChannel.in_app,
        subject="Execution Stuck",
        body="Execution {execution_id} has been running for {duration}",
        metadata={"category": "warning"},
    ),
]
