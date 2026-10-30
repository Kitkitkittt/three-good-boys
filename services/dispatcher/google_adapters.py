"""Thin Google adapters for the dispatcher seams.

Imported by the entry point only: importing ``google.cloud.*`` at module import
time would pull credentials and network behaviour into every unit test. Each
adapter is a straight translation of one protocol call to one API call — no
retry policy, no state machine, no reconciliation logic lives here, because
that belongs to ``service`` and must stay testable with fakes.
"""
import hashlib

from .queue import CloudTasksQueue


def build_batch_client(project, region, spec_config, client=None):
    """Return a real BatchClient that creates a fully specified GPU job.

    ``spec_config`` is the deployment's approved execution contract (a
    :class:`~lifemate_cloud.batch.BatchJobConfig`): image digest, machine type,
    boot disk, bucket mounts, worker arguments and task limit. It is never
    derived from a browser request — the dispatcher only ever receives the
    run's pinned identity.
    """
    from google.cloud import batch_v1  # imported lazily on purpose

    class BatchApi:
        def __init__(self, client=None):
            # ``client`` is injected by tests, which must not look up application
            # default credentials just to build a proto payload.
            self._client = client or batch_v1.BatchServiceClient(
                client_options={"api_endpoint": f"{region}-batch.googleapis.com"}
            )
            self._parent = f"projects/{project}/locations/{region}"

        def job_for(self, job_id, request_id, spec):
            """The CreateJob payload, built without any client or network.

            Split out so the proto shape is testable in-process. ``Volume.gcs``
            takes the top-level ``batch_v1.GCS`` message, whose only field is
            ``remote_path`` (``bucket`` or ``bucket/subdir``); the previous
            ``Volume.GCS(source=..., ...)`` pair does not exist, so no mount was
            ever declared.
            """
            job = batch_v1.Job()
            job.labels = {"request-id": request_id, "run-id": spec.run_id}
            job.task_groups = [self._task_group(spec)]
            allocation = job.allocation_policy
            allocation.service_account = {
                "email": spec_config.service_account,
                "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
            }
            allocation.instances = [{
                "policy": {
                    "machine_type": spec_config.machine_type,
                    "provisioning_model": batch_v1.AllocationPolicy.ProvisioningModel.STANDARD,
                    "boot_disk": {"type_": spec_config.boot_disk_type, "size_gb": spec_config.boot_disk_gb},
                }
            }]
            allocation.labels = {"run-id": spec.run_id}
            return job

        def create_job(self, job_id, request_id, spec):
            request = batch_v1.CreateJobRequest(
                parent=self._parent, job=self.job_for(job_id, request_id, spec),
                job_id=job_id, request_id=request_id)
            # ``Job.uid`` is output-only and is not a constructor argument; the
            # created job's name is what the API can address afterwards.
            created = self._client.create_job(request=request)
            # The index is keyed by the full job name and holds the uid, because
            # ``uid`` may be empty on the create response while ``name`` exists.
            return created.name or job_id, created.uid or ""

        def _task_group(self, spec):
            """One foreground task.

            The image's ENTRYPOINT is the worker module, so ``commands`` is the
            argument list only: setting it to a full ``python -m ...`` line would
            replace the entrypoint rather than append to it. GCS mounts are
            volumes on the task spec; they are not persistent disks, so no
            attached disk is declared.
            """
            group = batch_v1.TaskGroup()
            group.task_count = 1
            group.parallelism = 1
            runnable = batch_v1.Runnable()
            runnable.container = batch_v1.Runnable.Container()
            runnable.container.image_uri = spec_config.image
            runnable.container.commands = list(spec_config.arguments)
            for name, value in spec_config.env(spec.run_id, spec.attempt).items():
                runnable.environment.variables[name] = value
            group.task_spec = batch_v1.TaskSpec(runnables=[runnable], max_retry_count=spec_config.max_retry_count)
            group.task_spec.volumes = [batch_v1.Volume(
                gcs=batch_v1.GCS(remote_path=f"{mount.bucket}/{mount.remote_path}".rstrip("/")),
                mount_path=mount.mount_path,
                mount_options=list(mount.options),
            ) for mount in spec_config.mounts]
            return group

        def get_job(self, job_id):
            from google.api_core import exceptions as gexc

            try:
                job = self._client.get_job(name=f"{self._parent}/jobs/{job_id}")
            except gexc.NotFound:
                return None
            return {"name": job.name, "uid": job.uid, "phase": job.status.state.name, "state": _state(job)}

        def cancel_job(self, job_id):
            from google.api_core import exceptions as gexc

            try:
                self._client.cancel_job(name=f"{self._parent}/jobs/{job_id}")
            except gexc.NotFound:
                return None
            return self.get_job(job_id)

    return BatchApi(client=client)


def batch_config(env):
    """The approved execution contract, built from the dispatcher environment.

    Every value is deployment configuration supplied by Terraform, not request
    input, so a run cannot pick its own image, machine, tier or mount.
    """
    from lifemate_cloud.batch import BatchJobConfig, Mount

    mounts = []
    for raw in filter(None, (env.get("BATCH_MOUNTS") or "").split(";")):
        parts = raw.split()
        if len(parts) not in (3, 4):
            raise ValueError(f"BATCH_MOUNTS entry must be 'bucket remote path [options]': {raw!r}")
        bucket, remote, path = parts[:3]
        options = tuple(parts[3].split(",")) if len(parts) == 4 else ()
        mounts.append(Mount(bucket=bucket, remote_path=remote, mount_path=path, options=options))
    # Arguments only: the image's ENTRYPOINT already runs the worker module, so
    # a "python -m ..." prefix here would replace it and drop the launcher flags.
    arguments = tuple(env["BATCH_ARGUMENTS"].split())
    return BatchJobConfig(
        image=env["BATCH_IMAGE"],
        # The worker runs as its own identity, not the machine invoker's: the
        # task caller has Cloud Run invoke rights and nothing else by design.
        service_account=env["BATCH_SERVICE_ACCOUNT"],
        machine_type=env.get("BATCH_MACHINE_TYPE", "g2-standard-4"),
        boot_disk_type=env.get("BATCH_BOOT_DISK_TYPE", "pd-balanced"),
        boot_disk_gb=int(env.get("BATCH_BOOT_DISK_GB", "100")),
        task_timeout_seconds=int(env.get("TASK_TIMEOUT_SECONDS", "3600")),
        max_retry_count=int(env.get("BATCH_MAX_RETRIES", "0")),
        mounts=tuple(mounts),
        arguments=arguments,
    )


def _state(job):
    """Map the Batch phase to the four outcomes the dispatcher acts on."""
    name = job.status.state.name
    if name in ("SUCCEEDED", "FAILED", "CANCELLED"):
        return name
    if name in ("QUEUED", "SCHEDULED", "RUNNING"):
        return "ACTIVE"
    return "UNKNOWN"


def build_queue_client(env):
    """Return a QueueClient that creates one Cloud Tasks dispatch task."""
    return CloudTasksQueue(
        env["DISPATCH_URL"],
        env["TASK_SERVICE_ACCOUNT"],
        project=env["PROJECT_ID"],
        location=env["TASKS_LOCATION"],
        queue=env["TASKS_QUEUE"],
        audience=env["DISPATCH_AUDIENCE"],
    )


def build_clock():
    import time

    class SystemClock:
        def now(self):
            return time.time()

    return SystemClock()


def build_manifest_store(bucket):
    """Return the dispatcher's manifest store over the results bucket.

    The worker publishes one :class:`ResultManifest` document per run; the
    dispatcher reads exactly that object. A missing document is a missing
    manifest, which fails closed rather than succeeding without evidence.
    """
    import json

    from lifemate_cloud.manifest import ResultManifest

    class GcsManifests:
        def __init__(self, client=None):
            self._bucket = (client or _storage_client()).bucket(bucket)

        def read(self, run_id):
            blob = self._bucket.blob(f"manifests/{run_id}.json")
            if not blob.exists():
                return None
            return ResultManifest.from_dict(json.loads(blob.download_as_bytes()))

    return GcsManifests()


def build_artifact_store(bucket):
    """Return an ArtifactStore backed by generation-pinned GCS objects.

    Each manifest entry pins one generation and a lowercase sha256 of the
    object's bytes. Verification reloads that exact generation and hashes its
    content, so an overwritten or truncated object cannot masquerade as the
    committed artifact. GCS metadata checksums are deliberately not used: they
    are crc32c/md5 and would compare unequal to the pinned sha256 even for
    identical bytes.
    """
    class GcsArtifacts:
        def __init__(self, client=None):
            self._bucket = (client or _storage_client()).bucket(bucket)

        def verify(self, manifest, prefix=""):
            for entry in manifest.entries:
                blob = self._bucket.blob(prefix + entry.name, generation=entry.generation)
                observed = hashlib.sha256(blob.download_as_bytes()).hexdigest()
                if observed != entry.checksum:
                    raise RuntimeError(
                        f"{entry.name} generation {entry.generation} hashes to "
                        f"{observed}, not the pinned {entry.checksum}"
                    )
            return manifest

    return GcsArtifacts()


def _storage_client():
    from google.cloud import storage  # imported lazily on purpose

    return storage.Client()
