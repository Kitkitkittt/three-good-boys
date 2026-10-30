"""Domain errors shared by the API, dispatcher and worker."""


class CloudError(Exception):
    """Base class so services can map one family of failures."""


class Unauthorized(CloudError):
    """The caller's role does not permit the action."""


class Conflict(CloudError):
    """An identity is already in use for different content."""


class InvalidTransition(CloudError):
    """A run state change is not in the state machine."""


class IncompleteManifest(CloudError):
    """A manifest does not cover each required object exactly once."""


class ManifestConflict(CloudError):
    """An object's content differs from what the manifest already pins."""
