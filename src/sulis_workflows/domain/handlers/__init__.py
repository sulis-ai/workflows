"""Domain handlers with @operation decorators.

ServiceSpec §3: Operations
Handlers contain business logic and emit CloudEvents.
"""

from sulis_workflows.domain.handlers.execution_handler import ExecutionHandler

__all__ = [
    "ExecutionHandler",
]
