"""Durable experiment creation: one transaction persists a real instance.

A teammate names an approved experiment template and an approved dataset/model;
the server mints a run-free experiment id, derives benchmark identity from the
template (never from the caller) and persists the instance. The create is
user-scoped and idempotent exactly like run acceptance: same user + same key +
same canonical body returns the stored instance, a different body conflicts.

Instances are the unit the dashboard creates and submits against; a path that
names a registered template directly keeps the pre-existing submission route
working.
"""
import dataclasses
import hashlib
import json

from lifemate_cloud.errors import Conflict
from lifemate_cloud.roles import Action, require

from .catalog import ExperimentInstance


def creation_fingerprint(user, template_id, dataset_id, model_id, label):
    """Stable identity of one create request, independent of key or mint time.

    A single hashed canonical string (never separate fields) so the idempotency
    document stays a thin, verifiable pointer.
    """
    canonical = json.dumps(
        {
            "user": user,
            "template_id": template_id,
            "dataset_id": dataset_id,
            "model_id": model_id,
            "label": label,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclasses.dataclass
class ExperimentService:
    """Creates durable experiment instances over the shared API repository."""

    repository: object
    new_experiment_id: object = lambda: __import__("uuid").uuid4().hex

    def create(self, user, role, key, template, dataset, model, label, created_at):
        """Persist an instance. Same user+key+body returns the stored instance."""
        require(role, Action.SUBMIT_RUN)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key must be a non-empty string")
        fingerprint = creation_fingerprint(user, template.id, dataset.id, model.id, label)
        record = self.repository.creation_record(user, key)
        if record is not None:
            stored_fingerprint, experiment_id = record
            if stored_fingerprint != fingerprint:
                raise Conflict(f"idempotency key {key!r} was used for a different creation")
            return self.repository.get_experiment(experiment_id)
        instance = ExperimentInstance(
            experiment_id=self.new_experiment_id(),
            template_id=template.id,
            benchmark_id=template.benchmark_id,
            dataset_id=dataset.id,
            model_id=model.id,
            label=label,
            decoding=dict(template.decoding),
            mode=template.mode,
            content_hash=template.content_hash,
            created_by=user,
            created_at=created_at,
        )
        # The transaction is the guarantee: a concurrent writer with the same
        # key wins, and this call returns the committed instance, not its own.
        return self.repository.commit_experiment(user, key, fingerprint, instance)
