from __future__ import annotations

from feast import Entity, FeatureView
from feast.permissions.action import AuthzedAction
from feast.permissions.permission import Permission
from feast.permissions.policy import RoleBasedPolicy

# ---------------------------------------------------------------------------
# Admin permission -- full CRUD and online read/write
# ---------------------------------------------------------------------------

admin_permission: Permission = Permission(
    name="admin_permission",
    types=[FeatureView, Entity],
    actions=[
        AuthzedAction.CREATE,
        AuthzedAction.DESCRIBE,
        AuthzedAction.UPDATE,
        AuthzedAction.DELETE,
        AuthzedAction.READ_ONLINE,
        AuthzedAction.WRITE_ONLINE,
    ],
    policy=RoleBasedPolicy(roles=["admin"]),
)

# ---------------------------------------------------------------------------
# Reader permission -- describe and online read only
# ---------------------------------------------------------------------------

reader_permission: Permission = Permission(
    name="reader_permission",
    types=[FeatureView, Entity],
    actions=[
        AuthzedAction.DESCRIBE,
        AuthzedAction.READ_ONLINE,
    ],
    policy=RoleBasedPolicy(roles=["reader"]),
)
