"""Owner-registered catalogs and the server-side resolution of a run request.

The browser sends only ``dataset_id``, ``model_id``, ``mode`` and ``decoding`` plus
the experiment in the path (plan §4). Everything that costs money or pins
provenance — hashes, machine tier, region, timeout, retry allowance, source SHA,
image digest, input object generations — is looked up here, never accepted from
the caller.
"""
import dataclasses

from lifemate_cloud.errors import CloudError
from lifemate_cloud.requests import RunRequest

# Request fields the API models for run submission and experiment-instance
# creation. Anything else is rejected before the domain sees it, so adding a
# field is a deliberate contract change.
#
# A run submission names an approved experiment (path), a dataset and a model.
# An experiment instance is created from an approved template plus the same
# concrete dataset/model choices; every policy and provenance value (benchmark,
# mode, decoding, tier, region, timeout, retries, image, source) stays on the
# template, never on the request.
SUBMIT_FIELDS = ("dataset_id", "model_id", "decoding")
CREATE_FIELDS = ("template_id", "dataset_id", "model_id", "label")


class UnknownArtifact(CloudError):
    """The caller named a dataset/model/experiment that is not owner-registered."""

    def __init__(self, kind, identifier):
        super().__init__(f"unknown {kind} {identifier!r}")
        self.kind = kind
        self.identifier = identifier


@dataclasses.dataclass(frozen=True)
class Artifact:
    """An approved dataset or model the team may reference by id."""

    id: str
    label: str
    hash: str
    objects: dict  # object name -> pinned generation


@dataclasses.dataclass(frozen=True)
class Experiment:
    id: str
    label: str
    benchmark_id: str
    cases: int
    content_hash: str
    mode: str
    decoding: dict
    expected_names: tuple = ()


@dataclasses.dataclass(frozen=True)
class ExperimentInstance:
    """A persisted experiment a teammate created, resolved from a template.

    Holds no independent policy: it records which approved template it came from
    and the concrete dataset/model it will run, so :meth:`Catalog.resolve` builds
    exactly one canonical request and nine-month audit can name both ids.
    """

    experiment_id: str
    template_id: str
    benchmark_id: str
    dataset_id: str
    model_id: str
    label: str
    decoding: dict
    mode: str
    content_hash: str
    created_by: str
    created_at: str




@dataclasses.dataclass(frozen=True)
class Catalog:
    """Owner-registered templates (datasets, models, experiments) plus run policy.

    Policy values (tier, region, timeout, retries, source SHA, image digest) are
    deployment configuration, not per-request input (plan §4).
    """

    datasets: dict
    models: dict
    experiments: dict
    machine_type: str
    region: str
    timeout_seconds: int
    retry_allowance: int
    source_sha: str
    image_digest: str
    decoding_defaults: dict = dataclasses.field(default_factory=dict)
    deadline_seconds: int = None

    def experiment(self, experiment_id):
        """An owner-registered experiment template, or raise UnknownArtifact."""
        experiment = self.experiments.get(experiment_id)
        if experiment is None:
            raise UnknownArtifact("experiment", experiment_id)
        return experiment

    def resolve_template(self, template_id, client_request):
        """Validate a create body against a template; return its pinned data.

        The body names only an approved dataset and model (and an optional label);
        hashes, objects, decoding, benchmark, image, tier and region come from the
        template/registry, never from the caller.
        """
        unknown = set(client_request) - set(CREATE_FIELDS)
        if unknown:
            raise UnknownArtifact("request field", sorted(unknown)[0])
        for name in ("dataset_id", "model_id"):
            value = client_request.get(name)
            if not isinstance(value, str) or not value:
                raise UnknownArtifact("request field", f"missing {name}")
        template = self.experiment(template_id)
        dataset = self.datasets.get(client_request["dataset_id"])
        if dataset is None:
            raise UnknownArtifact("dataset", client_request["dataset_id"])
        model = self.models.get(client_request["model_id"])
        if model is None:
            raise UnknownArtifact("model", client_request["model_id"])
        label = client_request.get("label")
        if label is not None and not isinstance(label, str):
            raise UnknownArtifact("request field", "label must be a string")
        return template, dataset, model, (label or template.label)

    def experiment_for(self, experiment_id, lookup):
        """The persisted instance named by ``experiment_id``, or raise UnknownArtifact."""
        instance = lookup(experiment_id)
        if instance is None:
            raise UnknownArtifact("experiment", experiment_id)
        return instance

    def resolve(self, experiment_id, client_request, instance=None):
        """Build the immutable :class:`RunRequest` for an approved submission.

        ``instance`` is the persisted experiment instance when the path names one;
        its template supplies the pinned policy. Without an instance the path must
        name a registered template directly (the pre-existing submission route).
        """
        unknown = set(client_request) - set(SUBMIT_FIELDS) - {"experiment_id"}
        if unknown:
            raise UnknownArtifact("request field", sorted(unknown)[0])
        missing = [name for name in SUBMIT_FIELDS
                   if name not in client_request and name != "decoding"]
        if missing:
            raise UnknownArtifact("request field", f"missing {sorted(missing)}")
        # The body may repeat the experiment id for convenience; the path is
        # authoritative and a mismatch is refused rather than silently ignored.
        echoed = client_request.get("experiment_id")
        if echoed is not None and echoed != experiment_id:
            raise UnknownArtifact("experiment", echoed)
        if instance is not None:
            template = self.experiment(instance.template_id)
            # The instance pinned the dataset/model it was created with; a
            # submission that names a different one is a different experiment.
            if client_request["dataset_id"] != instance.dataset_id:
                raise UnknownArtifact("dataset", client_request["dataset_id"])
            if client_request["model_id"] != instance.model_id:
                raise UnknownArtifact("model", client_request["model_id"])
            dataset_id, model_id = instance.dataset_id, instance.model_id
        else:
            template = self.experiment(experiment_id)
            dataset_id = client_request["dataset_id"]
            model_id = client_request["model_id"]
        dataset = self.datasets.get(dataset_id)
        if dataset is None:
            raise UnknownArtifact("dataset", dataset_id)
        model = self.models.get(model_id)
        if model is None:
            raise UnknownArtifact("model", model_id)
        decoding = dict(self.decoding_defaults)
        decoding.update(template.decoding)
        decoding.update(client_request.get("decoding") or {})
        inputs = dict(dataset.objects)
        inputs.update(model.objects)
        return RunRequest(
            dataset_id=dataset.id,
            dataset_hash=dataset.hash,
            model_id=model.id,
            model_hash=model.hash,
            mode=template.mode,
            decoding=decoding,
            benchmark_id=template.benchmark_id,
            machine_type=self.machine_type,
            region=self.region,
            timeout_seconds=self.timeout_seconds,
            retry_allowance=self.retry_allowance,
            source_sha=self.source_sha,
            image_digest=self.image_digest,
            inputs=inputs,
        )

    def approved(self):
        """The approved-artifact list the web tier may render."""
        return {
            "datasets": [{"id": item.id, "label": item.label} for item in self.datasets.values()],
            "models": [{"id": item.id, "label": item.label} for item in self.models.values()],
            "experiments": [
                {
                    "id": item.id,
                    "label": item.label,
                    "benchmark_id": item.benchmark_id,
                    "cases": item.cases,
                }
                for item in self.experiments.values()
            ],
        }
