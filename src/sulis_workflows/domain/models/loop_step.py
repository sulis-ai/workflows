"""LoopStep - Loop step configuration for batch workflows.

ServiceSpec §3.9: Batch Operations
Defines a loop step that processes items until a condition is met.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class LoopCondition(str, Enum):
    """Conditions for loop continuation.

    Determines when the loop step should continue processing.
    """

    queue_has_items = "queue.has_items()"
    """Continue while the bound queue has items."""

    items_remaining = "items_remaining > 0"
    """Continue while there are items remaining to process."""

    until_empty = "until_empty"
    """Continue until the queue is empty."""


class LoopStep(BaseModel):
    """Configuration for a loop step in batch workflows.

    ServiceSpec §3.9: Batch Operations

    A loop step processes items repeatedly until a condition is met.
    Used in batch workflows for high-volume processing like webhook
    delivery or data migration.

    Attributes:
        name: Step name for logging and debugging
        condition: Condition that must be true to continue looping
        max_iterations: Maximum loop iterations (safety limit)
        batch_size: Override batch size for this step (optional)
        continue_on_error: Whether to continue processing on errors
        timeout_seconds: Maximum execution time in seconds (optional)
    """

    name: str = Field(
        ...,
        description="Step name for logging and debugging",
    )
    condition: LoopCondition = Field(
        default=LoopCondition.queue_has_items,
        description="Condition that must be true to continue looping",
    )
    max_iterations: int = Field(
        default=10000,
        ge=1,
        alias="maxIterations",
        description="Maximum loop iterations (safety limit)",
    )
    batch_size: int | None = Field(
        default=None,
        ge=1,
        alias="batchSize",
        description="Override batch size for this step (optional)",
    )
    continue_on_error: bool = Field(
        default=False,
        alias="continueOnError",
        description="Whether to continue processing on errors",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        alias="timeoutSeconds",
        description="Maximum execution time in seconds (optional)",
    )

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "examples": [
                {
                    "name": "process_deliveries",
                    "condition": "queue.has_items()",
                    "maxIterations": 1000,
                    "batchSize": 50,
                    "continueOnError": True,
                    "timeoutSeconds": 300,
                },
            ],
        },
    }
