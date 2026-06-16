"""Role definitions for workflow service.

ServiceSpec §6: Roles - Predefined roles for workflow authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WorkflowPermission(str, Enum):
    """Permissions for workflow operations.

    ServiceSpec §5: Permissions - Permission definitions.
    """

    CREATE = "workflows.executions:create"
    READ = "workflows.executions:read"
    UPDATE = "workflows.executions:update"
    DELETE = "workflows.executions:delete"
    ADMIN = "workflows.*"


@dataclass(frozen=True)
class WorkflowRole:
    """Role definition for workflows.

    ServiceSpec §6: Roles - Role with permissions mapping.
    """

    name: str
    description: str
    permissions: frozenset[WorkflowPermission]


# Predefined roles per ServiceSpec §6
WORKFLOWS_ADMIN = WorkflowRole(
    name="workflows_admin",
    description="Full access to all workflow operations",
    permissions=frozenset([WorkflowPermission.ADMIN]),
)

WORKFLOWS_OPERATOR = WorkflowRole(
    name="workflows_operator",
    description="Create, read, and manage workflow executions",
    permissions=frozenset(
        [
            WorkflowPermission.CREATE,
            WorkflowPermission.READ,
            WorkflowPermission.UPDATE,
        ]
    ),
)

WORKFLOWS_VIEWER = WorkflowRole(
    name="workflows_viewer",
    description="Read-only access to workflow executions",
    permissions=frozenset([WorkflowPermission.READ]),
)


# Role registry for lookup
WORKFLOW_ROLES: dict[str, WorkflowRole] = {
    WORKFLOWS_ADMIN.name: WORKFLOWS_ADMIN,
    WORKFLOWS_OPERATOR.name: WORKFLOWS_OPERATOR,
    WORKFLOWS_VIEWER.name: WORKFLOWS_VIEWER,
}


def get_role(role_name: str) -> WorkflowRole | None:
    """Get role by name.

    Args:
        role_name: Name of role to look up

    Returns:
        WorkflowRole if found, None otherwise
    """
    return WORKFLOW_ROLES.get(role_name)


def has_permission(role: WorkflowRole, permission: WorkflowPermission) -> bool:
    """Check if role has a specific permission.

    Args:
        role: Role to check
        permission: Permission to check for

    Returns:
        True if role has permission (directly or via admin)
    """
    # Admin permission grants all access
    if WorkflowPermission.ADMIN in role.permissions:
        return True
    return permission in role.permissions
