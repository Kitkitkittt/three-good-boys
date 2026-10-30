"""Dispatcher outcomes that callers must distinguish from success.

These extend ``lifemate_cloud.errors.CloudError`` so the API, dispatcher and
worker map one failure family. The names say what must *not* happen: an
ambiguous outcome is a held slot, never a retry that spends twice.
"""
from lifemate_cloud.errors import CloudError


def code_for(error):
    """The stable failure code the API view redacts against.

    ``Run.failure_reason`` is documented as ``CODE`` or ``CODE: detail``; the
    detail is never rendered. The code is the exception class name upper-cased
    (``AmbiguousOutcome`` -> ``AMBIGUOUSOUTCOME``) so a detail can never be
    mistaken for a code when the text is later split.
    """
    return type(error).__name__.upper()


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
