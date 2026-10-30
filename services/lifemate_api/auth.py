"""Verify the forwarded signed IAP assertion and map it to an application role.

The IAP JWT is the only identity source. An ``X-Goog-Authenticated-User-Email``
header is attacker-controlled when the service is reachable without IAP, so this
module never reads it.

Verification is four checks in this order: signature (delegated to an injected
verifier so production can use Google's key set and tests can sign locally),
issuer, audience, expiry. Only then is the assertion's ``email`` claim read.
"""
import dataclasses
import datetime

from lifemate_cloud.errors import CloudError

IAP_ISSUER = "https://cloud.google.com/iap"
ASSERTION_HEADER = "x-goog-iap-jwt-assertion"


class AuthError(CloudError):
    """The caller presented no verifiable IAP identity."""


@dataclasses.dataclass(frozen=True)
class Identity:
    """A verified caller: the assertion's email plus its resolved application role."""

    email: str
    role: object


def _expiry_moment(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthError("iap assertion has no numeric exp")
    return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)


def verify_assertion(assertion, verifier, audience, now=None, issuer=IAP_ISSUER):
    """Return the verified claims of ``assertion`` or raise :class:`AuthError`.

    ``verifier(assertion)`` must raise on a bad signature and return the decoded
    claims on success. Everything else is checked here so a swapped verifier
    cannot skip issuer, audience or expiry.
    """
    if not isinstance(assertion, str) or not assertion.strip():
        raise AuthError("missing iap assertion")
    if not isinstance(audience, str) or not audience.strip():
        raise AuthError("server has no configured iap audience")
    try:
        claims = verifier(assertion)
    except Exception as exc:  # signature/format failures must not leak as 500s
        raise AuthError(f"iap signature verification failed: {type(exc).__name__}") from exc
    if not isinstance(claims, dict):
        raise AuthError("iap verifier returned no claims")
    if claims.get("iss") != issuer:
        raise AuthError("iap assertion issuer is not accepted")
    if claims.get("aud") != audience:
        raise AuthError("iap assertion audience does not match this service")
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    if _expiry_moment(claims.get("exp")) <= moment:
        raise AuthError("iap assertion has expired")
    email = claims.get("email")
    if not isinstance(email, str) or not email.strip():
        raise AuthError("iap assertion carries no verified email")
    return {"email": email.strip(), "claims": claims}


def resolve_identity(assertion, verifier, audience, roles, now=None):
    """Verify the assertion and map its email to an application role.

    ``roles`` maps a verified email to a ``Role``; an email with no grant is
    refused rather than given a default role.
    """
    verified = verify_assertion(assertion, verifier, audience, now=now)
    email = verified["email"]
    role = roles.get(email)
    if role is None:
        raise AuthError(f"unknown team member {email!r}")
    return Identity(email=email, role=role)


IAP_JWKS_URL = "https://www.gstatic.com/iap/verify/public_key-jwk"
IAP_ALGORITHMS = ("ES256",)


def iap_verifier(audience, jwks_url=IAP_JWKS_URL, algorithms=IAP_ALGORITHMS):
    """A verifier backed by Google's published IAP key set.

    aud/iss/exp are still checked in :func:`verify_assertion`; this only proves
    the signature. The key client is built lazily on first use, so importing this
    module needs no network.
    """
    state = {}

    def _verify(assertion):
        import jwt  # PyJWT; present in the API image, not a Google client

        client = state.get("client")
        if client is None:
            client = state["client"] = jwt.PyJWKClient(jwks_url)
        signing_key = client.get_signing_key_from_jwt(assertion)
        return jwt.decode(
            assertion,
            signing_key.key,
            algorithms=list(algorithms),
            audience=audience,
            issuer=IAP_ISSUER,
        )

    return _verify
