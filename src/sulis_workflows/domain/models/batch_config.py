"""BatchProcessingConfig - Configuration for Worker Pool batch processing.

ServiceSpec §3.9: Batch Operations
Configures how Worker Pools process batches of work.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel, Field, field_validator


class BatchProcessingConfig(BaseModel):
    """Configuration for Worker Pool batch processing.

    ServiceSpec §3.9: Batch Operations

    Controls how Worker Pools pull and process batches of work items.
    Used by workflows bound to queues for high-volume processing.

    Attributes:
        batch_size: Number of items to process per batch (1-1000)
        keep_alive_timeout: Duration to keep worker alive between batches
        max_idle_time: Maximum idle time before worker shuts down
        max_items_per_run: Maximum total items to process before restart
    """

    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        alias="batchSize",
        description="Number of items to process per batch (1-1000)",
    )
    keep_alive_timeout: timedelta = Field(
        default=timedelta(seconds=60),
        alias="keepAliveTimeout",
        description="Duration to keep worker alive between batches (e.g., PT60S)",
    )
    max_idle_time: timedelta = Field(
        default=timedelta(seconds=30),
        alias="maxIdleTime",
        description="Maximum idle time before worker shuts down",
    )
    max_items_per_run: int = Field(
        default=1000,
        ge=1,
        alias="maxItemsPerRun",
        description="Maximum total items to process before restart",
    )

    @field_validator("keep_alive_timeout", "max_idle_time", mode="before")
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
                    "batchSize": 100,
                    "keepAliveTimeout": 60,
                    "maxIdleTime": 30,
                    "maxItemsPerRun": 1000,
                },
            ],
        },
    }
