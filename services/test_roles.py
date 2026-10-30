"""Role checks are the admission gate in front of every persistence write."""
import unittest

from lifemate_cloud.errors import Unauthorized
from lifemate_cloud.roles import Action, Role, authorize, require


class RoleTests(unittest.TestCase):
    def test_researcher_submits_reads_and_cancels_own_runs(self):
        for action in (Action.SUBMIT_RUN, Action.READ_RUN, Action.CANCEL_RUN):
            self.assertTrue(authorize(Role.RESEARCHER, action))

    def test_researcher_cannot_manage_or_approve_artifacts(self):
        for action in (Action.APPROVE_ARTIFACT, Action.MANAGE_ARTIFACTS):
            self.assertFalse(authorize(Role.RESEARCHER, action))
            with self.assertRaises(Unauthorized):
                require(Role.RESEARCHER, action)

    def test_viewer_reads_approved_metadata_only(self):
        self.assertTrue(authorize(Role.VIEWER, Action.READ_RUN))
        for action in (
            Action.SUBMIT_RUN,
            Action.CANCEL_RUN,
            Action.APPROVE_ARTIFACT,
            Action.SET_COST_POLICY,
        ):
            self.assertFalse(authorize(Role.VIEWER, action))

    def test_maintainer_manages_artifacts_but_not_cost_policy(self):
        for action in (
            Action.SUBMIT_RUN,
            Action.READ_RUN,
            Action.CANCEL_RUN,
            Action.APPROVE_ARTIFACT,
            Action.MANAGE_ARTIFACTS,
        ):
            self.assertTrue(authorize(Role.MAINTAINER, action))
        self.assertFalse(authorize(Role.MAINTAINER, Action.SET_COST_POLICY))

    def test_owner_covers_every_action(self):
        for action in Action:
            self.assertTrue(authorize(Role.OWNER, action))

    def test_require_rejects_with_role_and_action_named(self):
        with self.assertRaises(Unauthorized) as caught:
            require(Role.VIEWER, Action.SUBMIT_RUN)
        message = str(caught.exception)
        self.assertIn(Role.VIEWER.value, message)
        self.assertIn(Action.SUBMIT_RUN.value, message)

    def test_require_passes_for_permitted_action(self):
        require(Role.OWNER, Action.SET_COST_POLICY)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(Unauthorized):
            require("superuser", Action.READ_RUN)


if __name__ == "__main__":
    unittest.main()
