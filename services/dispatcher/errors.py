"""Dispatcher outcomes that callers must distinguish from success.

These extend ``lifemate_cloud.errors.CloudError`` so the API, dispatcher and
worker map one failure family. The names say what must *not* happen: an
ambiguous outcome is a held slot, never a retry that spends twice.
"""
from lifemate_cloud.errors import CloudError


class AmbiguousOutcome(CloudError):
    """A create/cancel/terminate call may or may not have landed.

    The slot stays held, an alert is recorded and the same identity is retried;
    issuing a new job would risk duplicate spend.
    """


class LedgerOverflow(CloudError):
    """The requested reservation exceeds the admitted budget, or one is unsettled."""


class DeadlineExceeded(CloudError):
    """The whole-run deadline elapsed; the run is cancelled, not silently extended."""


class VerifiedSuccess(CloudError):
    """Batch reported success but the artifact manifest did not verify."""
