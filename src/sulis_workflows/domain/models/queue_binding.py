"""QueueBinding - Queue trigger configuration for workflows.

ServiceSpec §3.9: Batch Operations
Binds a workflow to a message queue for automatic triggering.
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class QueueType(str, Enum):
    """Supported queue types for workflow bindings.

    Determines the message queue infrastructure used.
    """

    pubsub = "pubsub"
    """Google Cloud Pub/Sub for high-throughput messaging."""

    cloud_tasks = "cloud_tasks"
    """Google Cloud Tasks for task queuing with retry support."""

    memory = "memory"
    """In-memory queue for testing purposes."""


class QueueBinding(BaseModel):
    """Configuration for binding a workflow to a message queue.

    ServiceSpec §3.9: Batch Operations

    When a workflow has a queue binding, it is automatically triggered
    when messages arrive on the bound queue. Supports batching for
    high-volume processing.

    Attributes:
        queue_name: Name of the queue to bind to
        queue_type: Type of queue (pubsub, cloud_tasks, memory)
        subscription_id: Subscription ID for Pub/Sub bindings
        batch_size: Number of messages to pull per batch (1-1000)
        batch_timeout: Maximum time to wait for a full batch
        max_delivery_attempts: Maximum delivery attempts before DLQ
        dead_letter_queue: Queue for failed messages (optional)
    """

    queue_name: str = Field(
        ...,
        alias="queueName",
        description="Name of the queue to bind to",
    )
    queue_type: QueueType = Field(
        default=QueueType.pubsub,
        alias="queueType",
        description="Type of queue (pubsub, cloud_tasks, memory)",
    )
    subscription_id: str | None = Field(
        default=None,
        alias="subscriptionId",
        description="Subscription ID for Pub/Sub bindings",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        alias="batchSize",
        description="Number of messages to pull per batch (1-1000)",
    )
    batch_timeout: timedelta = Field(
        default=timedelta(seconds=5),
        alias="batchTimeout",
        description="Maximum time to wait for a full batch (e.g., PT5S)",
    )
    max_delivery_attempts: int = Field(
        default=3,
        ge=1,
        alias="maxDeliveryAttempts",
        description="Maximum delivery attempts before DLQ",
    )
    dead_letter_queue: str | None = Field(
        default=None,
        alias="deadLetterQueue",
        description="Queue for failed messages (optional)",
    )

    @field_validator("batch_timeout", mode="before")
    @classmethod
    def convert_seconds_to_timedelta(cls, v: timedelta | int | float) -> timedelta:
        """Convert seconds to timedelta if needed."""
        if isinstance(v, timedelta):
            return v
        return timedelta(seconds=v)

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "queueName": "webhook-deliveries",
                    "queueType": "pubsub",
                    "subscriptionId": "sub-webhook-worker",
                    "batchSize": 100,
                    "batchTimeout": 5,
                    "maxDeliveryAttempts": 5,
                },
            ],
        },
    }
