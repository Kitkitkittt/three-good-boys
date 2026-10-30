"""IAP assertion verification: signature, issuer, audience, expiry, then email."""
import datetime
import unittest

import jwt

from lifemate_api.auth import AuthError, IAP_ISSUER, resolve_identity, verify_assertion
from lifemate_cloud.roles import Role

AUDIENCE = "/projects/123/global/backendServices/456"
SECRET = "test-signing-secret"
FUTURE = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
NOW = datetime.datetime(2026, 10, 30, tzinfo=datetime.timezone.utc)


def verifier(secret=SECRET, algorithms=("HS256",)):
    """A verifier that really checks the signature, like Google's key set does."""

    def _verify(assertion):
        return jwt.decode(assertion, secret, algorithms=list(algorithms), options={"verify_aud": False})

    return _verify


def sign(claims, secret=SECRET, algorithm="HS256"):
    return jwt.encode(claims, secret, algorithm=algorithm)


def claims(**overrides):
    base = {
        "iss": IAP_ISSUER,
        "aud": AUDIENCE,
        "exp": int(FUTURE.timestamp()),
        "email": "alice@example.com",
    }
    base.update(overrides)
    return base


class AssertionTests(unittest.TestCase):
    def verify(self, assertion, **kwargs):
        return verify_assertion(assertion, verifier(), AUDIENCE, now=NOW, **kwargs)

    def test_a_valid_assertion_yields_the_email_claim(self):
        result = self.verify(sign(claims()))
        self.assertEqual(result["email"], "alice@example.com")

    def test_bad_signature_is_rejected(self):
        with self.assertRaises(AuthError):
            self.verify(sign(claims(), secret="not-the-key"))

    def test_unsigned_alg_none_is_rejected(self):
        unsigned = jwt.encode(claims(), key="", algorithm="none")
        with self.assertRaises(AuthError):
            self.verify(unsigned)

    def test_wrong_issuer_is_rejected(self):
        with self.assertRaises(AuthError):
            self.verify(sign(claims(iss="https://accounts.google.com")))

    def test_wrong_audience_is_rejected(self):
        with self.assertRaises(AuthError):
            self.verify(sign(claims(aud="/projects/123/global/backendServices/999")))

    def test_expired_assertion_is_rejected(self):
        past = int((NOW - datetime.timedelta(minutes=1)).timestamp())
        with self.assertRaises(AuthError):
            self.verify(sign(claims(exp=past)))

    def test_missing_numeric_exp_is_rejected(self):
        for bad in ("soon", None, True):
            with self.assertRaises(AuthError, msg=bad):
                self.verify(sign(claims(exp=bad)))

    def test_missing_or_blank_email_is_rejected(self):
        for bad in (None, "", "   ", 5):
            with self.assertRaises(AuthError, msg=bad):
                self.verify(sign(claims(email=bad)))

    def test_blank_assertion_is_rejected_before_the_verifier_runs(self):
        called = []

        def verifier(_):
            called.append(1)
            return claims()

        with self.assertRaises(AuthError):
            verify_assertion("  ", verifier, AUDIENCE, now=NOW)
        self.assertEqual(called, [])

    def test_no_configured_audience_is_rejected(self):
        with self.assertRaises(AuthError):
            verify_assertion(sign(claims()), verifier(), "", now=NOW)


class IdentityMappingTests(unittest.TestCase):
    def test_a_known_email_maps_to_its_role(self):
        identity = resolve_identity(
            sign(claims()), verifier(), AUDIENCE, {"alice@example.com": Role.RESEARCHER}, now=NOW
        )
        self.assertEqual(identity.email, "alice@example.com")
        self.assertEqual(identity.role, Role.RESEARCHER)

    def test_an_unregistered_email_is_refused_with_no_default_role(self):
        with self.assertRaises(AuthError):
            resolve_identity(sign(claims()), verifier(), AUDIENCE, {"bob@example.com": Role.OWNER}, now=NOW)


if __name__ == "__main__":
    unittest.main()
