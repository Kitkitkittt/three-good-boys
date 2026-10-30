"""Machine-readable run views. Only approved metadata leaves this module.

The shapes match the web client's ``RunMeta``/``RunDetail`` (ticket 18). Request
inputs (object generations, decoding values, hashes), the fingerprint and raw
failure details are deliberately absent: the browser never needs them and they
may name restricted objects.

A run view echoes only *sanitized identity*: the approved experiment, dataset and
model ids, the benchmark id, the mode and a configuration digest. The digest is a
hash of the pinned configuration, never the configuration itself, so nothing in
it can be read back as a decoding value, an input object name or a trace.
"""
import dataclasses
import hashlib
import json

# Failure codes the worker/dispatcher may record; the summary string is fixed so
# a raw exception, traceback or restricted path never reaches the browser.
_REDACTED = {
    "batch_create_failed": "the GPU job could not be created",
    "batch_failed": "the GPU job reported a failure",
    "BATCH_FAILED": "the GPU job reported a failure",
    "deadline_exceeded": "the run exceeded its deadline",
    "manifest_incomplete": "results were incomplete",
    "manifest_conflict": "results conflicted with a pinned object",
    "worker_lost": "the worker stopped before finishing",
}


def redact(reason):
    """Map a stored failure reason to an approved {code, summary} pair."""
    if not reason:
        return None
    # Stored reasons are CODE or CODE: detail; the detail is never returned.
    code = str(reason).split(":", 1)[0].strip()
    return {"code": code, "summary": _REDACTED.get(code, "the run failed")}


def configuration_hash(request, benchmark_id):
    """Digest of the complete immutable execution configuration.

    Uses the canonical :meth:`RunRequest.fingerprint` so there is one identity
    convention, not a second partial one: mode, decoding, dataset/model hashes,
    pinned input object identities, source SHA, image digest, machine, region,
    timeout and retry allowance all participate. Two runs share this value only
    when they would execute identically; a changed image or source SHA changes
    it. The result is a digest, so no raw restricted field is exposed.
    """
    canonical = json.dumps(
        {"fingerprint": request.fingerprint(), "benchmark_id": benchmark_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def summarize(run, identity=None):
    """``RunMeta``: status, cancellation intent and sanitized identity."""
    view = {
        "run_id": run.run_id,
        "owner": run.owner,
        "state": run.state.value,
        "cancel_requested": run.cancel_requested,
        "batch_phase": run.batch_phase,
        "failure": redact(run.failure_reason),
    }
    view["benchmark_id"] = identity["benchmark_id"] if identity else None
    view["experiment_id"] = identity["experiment_id"] if identity else None
    view["dataset_id"] = identity["dataset_id"] if identity else None
    view["model_id"] = identity["model_id"] if identity else None
    view["mode"] = identity["mode"] if identity else None
    view["benchmark_hash"] = identity["benchmark_hash"] if identity else None
    view["benchmark_cases"] = identity["benchmark_cases"] if identity else None
    view["configuration_hash"] = configuration_hash(identity["request"], identity["benchmark_id"]) if identity else None
    return view


def identity_for(request, experiment_id=None, benchmark=None):
    """The sanitized identity a run echoes; ``request`` is the pinned RunRequest.

    ``benchmark`` is the ``(content_hash, cases)`` pair pinned at acceptance, so
    a revised benchmark under the same id stays distinguishable. It is read from
    the run's own record, never from the current catalog.
    """
    return {
        "request": request,
        "experiment_id": experiment_id,
        "benchmark_id": request.benchmark_id,
        "benchmark_hash": benchmark[0] if benchmark else None,
        "benchmark_cases": benchmark[1] if benchmark else None,
        "dataset_id": request.dataset_id,
        "model_id": request.model_id,
        "mode": request.mode,
    }


def experiment_view(instance, request, template):
    """The create response: a real instance plus the identity it will execute with.

    ``request`` is the canonical :class:`RunRequest` the instance resolves to, so
    the digest is the same one a run of this instance will echo. Benchmark content
    identity (owner-registered hash and case count) travels with it so a revised
    benchmark stays distinguishable. Decoding values, hashes of objects and object
    names are not returned: only ids, mode and digests.
    """
    return {
        "experiment_id": instance.experiment_id,
        "template_id": instance.template_id,
        "label": instance.label,
        "benchmark_id": instance.benchmark_id,
        "benchmark_hash": template.content_hash,
        "benchmark_cases": template.cases,
        "dataset_id": instance.dataset_id,
        "model_id": instance.model_id,
        "mode": instance.mode,
        "created_by": instance.created_by,
        "created_at": instance.created_at,
        "configuration_hash": configuration_hash(request, instance.benchmark_id),
    }


def artifact_view(entry):
    """Approved artifact metadata only: name, pinned generation, checksum, size.

    ``entry`` is a manifest entry (object name, generation, checksum, byte size).
    Object contents, signed URLs and bucket paths are never returned.
    """
    return {
        "name": entry.name,
        "generation": str(entry.generation),
        "checksum": entry.checksum,
        "bytes": getattr(entry, "size", None),
    }


def detail(run, identity=None, artifacts=()):
    """``RunDetail``: the summary plus approved artifact metadata (never content)."""
    view = summarize(run, identity)
    view["artifacts"] = [artifact_view(entry) for entry in artifacts]
    return view


def failure_view(run):
    """The redacted failure body for ``GET /api/runs/{id}/failures``."""
    return {"run_id": run.run_id, "state": run.state.value, "failure": redact(run.failure_reason)}
