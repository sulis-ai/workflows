"""Domain errors for async workflow execution.

ServiceSpec §10: Errors
Each error has:
- error_code: Machine-readable code
- http_status: HTTP status mapping
- Descriptive message for users
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sulis_workflows.domain.models.execution_state import ExecutionStatus


class WorkflowExecutionError(Exception):
    """Base class for workflow execution errors."""

    error_code: str = "WORKFLOW_EXECUTION_ERROR"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class WorkflowNotFoundError(WorkflowExecutionError):
    """Workflow definition not found.

    ServiceSpec §10: WORKFLOW_NOT_FOUND
    HTTP 404 - The specified workflow does not exist.
    """

    error_code: str = "WORKFLOW_NOT_FOUND"
    http_status: int = 404

    def __init__(self, workflow_id: str) -> None:
        self.workflow_id = workflow_id
        super().__init__(f"Workflow not found: {workflow_id}")


class ExecutionNotFoundError(WorkflowExecutionError):
    """Execution not found.

    ServiceSpec §10: EXECUTION_NOT_FOUND
    HTTP 404 - The specified execution does not exist.
    """

    error_code: str = "EXECUTION_NOT_FOUND"
    http_status: int = 404

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        super().__init__(f"Execution not found: {execution_id}")


class ExecutionNotCancellableError(WorkflowExecutionError):
    """Execution cannot be cancelled in its current state.

    ServiceSpec §10: EXECUTION_NOT_CANCELLABLE
    HTTP 400 - The execution is in a terminal state and cannot be cancelled.
    """

    error_code: str = "EXECUTION_NOT_CANCELLABLE"
    http_status: int = 400

    def __init__(self, execution_id: str, current_status: ExecutionStatus) -> None:
        self.execution_id = execution_id
        self.current_status = current_status
        super().__init__(
            f"Execution {execution_id} cannot be cancelled: "
            f"current status is {current_status.value}"
        )


class InvalidDelayError(WorkflowExecutionError):
    """Delay value exceeds maximum allowed.

    ServiceSpec §10: INVALID_DELAY
    HTTP 400 - The delay exceeds the maximum of 24 hours.
    """

    error_code: str = "INVALID_DELAY"
    http_status: int = 400

    def __init__(self, delay_seconds: int, max_delay_seconds: int) -> None:
        self.delay_seconds = delay_seconds
        self.max_delay_seconds = max_delay_seconds
        super().__init__(f"Delay of {delay_seconds}s exceeds maximum of {max_delay_seconds}s")


class DuplicateExecutionError(WorkflowExecutionError):
    """Execution with idempotency key already exists.

    ServiceSpec §10: DUPLICATE_EXECUTION
    HTTP 409 - An execution with this idempotency key already exists.
    """

    error_code: str = "DUPLICATE_EXECUTION"
    http_status: int = 409

    def __init__(self, idempotency_key: str, existing_execution_id: str) -> None:
        self.idempotency_key = idempotency_key
        self.existing_execution_id = existing_execution_id
        super().__init__(
            f"Execution with idempotency key '{idempotency_key}' already exists: "
            f"{existing_execution_id}"
        )


class TimeoutExceededError(WorkflowExecutionError):
    """Wait timeout exceeded.

    ServiceSpec §10: TIMEOUT_EXCEEDED
    HTTP 408 - The wait operation timed out.
    """

    error_code: str = "TIMEOUT_EXCEEDED"
    http_status: int = 408

    def __init__(self, execution_id: str, timeout_seconds: int) -> None:
        self.execution_id = execution_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Timeout of {timeout_seconds}s exceeded waiting for execution {execution_id}"
        )


class ExecutionNotRestorableError(WorkflowExecutionError):
    """Execution cannot be restored.

    ServiceSpec §10: EXECUTION_NOT_RESTORABLE
    HTTP 400 - The execution is not deleted and cannot be restored.
    """

    error_code: str = "EXECUTION_NOT_RESTORABLE"
    http_status: int = 400

    def __init__(self, execution_id: str) -> None:
        self.execution_id = execution_id
        super().__init__(f"Execution {execution_id} is not deleted and cannot be restored")


class ExecutionNotApprovableError(WorkflowExecutionError):
    """Execution cannot be approved in its current state.

    HTTP 400 - Execution must be in awaiting_approval status.
    """

    error_code: str = "EXECUTION_NOT_APPROVABLE"
    http_status: int = 400

    def __init__(self, execution_id: str, current_status: ExecutionStatus) -> None:
        self.execution_id = execution_id
        self.current_status = current_status
        super().__init__(
            f"Execution {execution_id} cannot be approved: current status is {current_status.value}"
        )


class ExecutionNotResumableError(WorkflowExecutionError):
    """Execution cannot be resumed in its current state.

    HTTP 400 - Execution must be in awaiting_event status.
    """

    error_code: str = "EXECUTION_NOT_RESUMABLE"
    http_status: int = 400

    def __init__(self, execution_id: str, current_status: ExecutionStatus) -> None:
        self.execution_id = execution_id
        self.current_status = current_status
        super().__init__(
            f"Execution {execution_id} cannot be resumed: current status is {current_status.value}"
        )


class CompilationError(WorkflowExecutionError):
    """Base class for all graph compilation errors.

    REL-ERR-04: HTTP 500 — compilation failures are internal errors
    unless a more specific subclass applies.
    """

    error_code: str = "COMPILATION_ERROR"
    http_status: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)


class GraphValidationError(CompilationError):
    """Graph structure fails validation rules.

    REL-ERR-01: HTTP 400 — invalid graph structure is a client input error.
    Supports both DAG and cyclic graphs (LangGraph native).
    """

    error_code: str = "GRAPH_VALIDATION_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, rule_id: str, node_id: str | None = None) -> None:
        self.rule_id = rule_id
        self.node_id = node_id
        super().__init__(message)


# Backwards compatibility alias
DAGValidationError = GraphValidationError


class NodeResolutionError(CompilationError):
    """Node spec_ref cannot be resolved to a callable.

    REL-ERR-02: HTTP 400 — the spec_ref points to something
    that doesn't exist or can't be loaded.
    """

    error_code: str = "NODE_RESOLUTION_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, spec_ref: str) -> None:
        self.spec_ref = spec_ref
        super().__init__(message)


class GateConfigError(CompilationError):
    """Gate node has invalid configuration.

    REL-ERR-03: HTTP 400 — the gate configuration in DAG.yaml is invalid.
    """

    error_code: str = "GATE_CONFIG_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, gate_id: str, gate_type: str | None = None) -> None:
        self.gate_id = gate_id
        self.gate_type = gate_type
        super().__init__(message)
