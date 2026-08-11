from feast.entity import Entity
from feast.feature_view import FeatureView
from feast.permissions.action import AuthzedAction
from feast.permissions.permission import Permission
from feast.permissions.policy import RoleBasedPolicy

admin_permission = Permission(
    name="admin_permission",
    types=[FeatureView, Entity],
    actions=[
        AuthzedAction.DESCRIBE,
        AuthzedAction.READ_ONLINE,
        AuthzedAction.WRITE_ONLINE,
        AuthzedAction.CREATE,
        AuthzedAction.UPDATE,
        AuthzedAction.DELETE,
    ],
    policy=RoleBasedPolicy(roles=["admin"]),
)

reader_permission = Permission(
    name="reader_permission",
    types=[FeatureView, Entity],
    actions=[AuthzedAction.DESCRIBE, AuthzedAction.READ_ONLINE],
    policy=RoleBasedPolicy(roles=["reader"]),
)
