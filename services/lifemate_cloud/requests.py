"""Canonical, immutable run request and its identity."""
import dataclasses
import hashlib
import json

from .errors import Conflict

_FIELDS = (
    "dataset_id",
    "dataset_hash",
    "model_id",
    "model_hash",
    "mode",
    "decoding",
    "benchmark_id",
    "machine_type",
    "region",
    "timeout_seconds",
    "retry_allowance",
    "source_sha",
    "image_digest",
    "inputs",
)
_REQUIRED_TEXT = (
    "dataset_id",
    "dataset_hash",
    "model_id",
    "model_hash",
    "mode",
    "benchmark_id",
    "machine_type",
    "region",
    "source_sha",
    "image_digest",
)


def _frozen(value):
    if isinstance(value, dict):
        return {str(key): _frozen(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@dataclasses.dataclass(frozen=True)
class RunRequest:
    """Every field the server resolved before accepting a run.

    Rationale for each field lives in the implementation plan; the class only
    enforces that once accepted, a request cannot change.
    """

    dataset_id: str
    dataset_hash: str
    model_id: str
    model_hash: str
    mode: str
    decoding: dict
    benchmark_id: str
    machine_type: str
    region: str
    timeout_seconds: int
    retry_allowance: int
    source_sha: str
    image_digest: str
    inputs: dict

    def __post_init__(self):
        for name in _REQUIRED_TEXT:
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("timeout_seconds", "retry_allowance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        for name in ("decoding", "inputs"):
            if not isinstance(getattr(self, name), dict):
                raise ValueError(f"{name} must be a dict")
            object.__setattr__(self, name, _frozen(getattr(self, name)))

    def payload(self):
        return {name: _plain(getattr(self, name)) for name in _FIELDS}

    def fingerprint(self):
        """SHA-256 over the canonical JSON: identity independent of key order."""
        return hashlib.sha256(canonical_json(self).encode()).hexdigest()

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise Conflict("request payload must be an object")
        unknown = set(payload) - set(_FIELDS)
        if unknown:
            raise Conflict(f"request has unsupported fields: {sorted(unknown)}")
        missing = set(_FIELDS) - set(payload)
        if missing:
            raise ValueError(f"request is missing fields: {sorted(missing)}")
        try:
            return cls(**{name: payload[name] for name in _FIELDS})
        except TypeError as exc:
            raise Conflict(f"request is not canonical: {exc}") from exc


def canonical_json(request):
    return json.dumps(request.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
