"""Application roles and the actions each may perform."""
from enum import Enum

from .errors import Unauthorized


class Role(str, Enum):
    OWNER = "owner"
    MAINTAINER = "maintainer"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class Action(str, Enum):
    READ_RUN = "read_run"
    SUBMIT_RUN = "submit_run"
    CANCEL_RUN = "cancel_run"
    MANAGE_ARTIFACTS = "manage_artifacts"
    APPROVE_ARTIFACT = "approve_artifact"
    SET_COST_POLICY = "set_cost_policy"


_READ_ALL = frozenset({Action.READ_RUN})

_PERMISSIONS = {
    Role.VIEWER: _READ_ALL,
    Role.RESEARCHER: _READ_ALL | {Action.SUBMIT_RUN, Action.CANCEL_RUN},
    Role.MAINTAINER: _READ_ALL
    | {Action.SUBMIT_RUN, Action.CANCEL_RUN, Action.MANAGE_ARTIFACTS, Action.APPROVE_ARTIFACT},
    Role.OWNER: frozenset(Action),
}


def _coerce(role):
    return role if isinstance(role, Role) else Role(role)


def authorize(role, action):
    """Return True when ``role`` may perform ``action``; unknown roles get nothing."""
    try:
        return action in _PERMISSIONS[_coerce(role)]
    except ValueError:
        return False


def require(role, action):
    """Raise Unauthorized unless ``role`` may perform ``action``."""
    if not authorize(role, action):
        raise Unauthorized(f"role {getattr(role, 'value', role)!r} may not {getattr(action, 'value', action)!r}")
