"""Deterministic Batch identity per (run_id, attempt)."""
import dataclasses
import hashlib
import re
import uuid

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def job_id_for(run_id, attempt):
    """Deterministic, Batch-legal job name. Retries reuse it."""
    attempt = int(attempt)
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    digest = hashlib.sha256(f"{run_id}\0{attempt}".encode()).hexdigest()[:24]
    return f"lmr-{digest}"


@dataclasses.dataclass(frozen=True)
class BatchJobSpec:
    """Identity pinned before the Batch create call. Persist it; never regenerate on retry."""

    job_id: str
    request_id: str
    run_id: str
    attempt: int
    request_fingerprint: str
    retry_count: int = 0

    def __post_init__(self):
        if not _NAME.match(self.job_id):
            raise ValueError(f"illegal Batch job name: {self.job_id!r}")
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")

    @classmethod
    def for_attempt(cls, run_id, attempt, request_fingerprint):
        digest = hashlib.sha256(f"{request_fingerprint}\0{run_id}\0{attempt}".encode()).hexdigest()[:32]
        return cls(
            job_id=job_id_for(run_id, attempt),
            request_id=str(uuid.UUID(digest)),
            run_id=run_id,
            attempt=int(attempt),
            request_fingerprint=request_fingerprint,
        )

    def with_retry(self, retry_count):
        """Batch task retry stays inside the same job, so only the counter moves."""
        return dataclasses.replace(self, retry_count=retry_count)


@dataclasses.dataclass(frozen=True)
class Mount:
    """One approved GCS mount: bucket, object prefix and container path."""

    bucket: str
    remote_path: str
    mount_path: str
    options: tuple = ()

    @property
    def device_name(self):
        return "gcs-" + hashlib.sha256(self.mount_path.encode()).hexdigest()[:12]

    def __post_init__(self):
        if not self.bucket or not self.mount_path.startswith("/"):
            raise ValueError(f"illegal mount: {self.bucket!r} -> {self.mount_path!r}")


@dataclasses.dataclass(frozen=True)
class BatchJobConfig:
    """The approved execution contract for a GPU job.

    Deployment configuration, never request input: the dispatcher only receives
    a run's pinned identity, so image, machine, mounts and task limit cannot be
    chosen by a browser. ``arguments`` are appended to the image's ENTRYPOINT;
    they never contain ``python -m`` or shell syntax, because Batch replaces the
    entrypoint with a full command string only when one is given. ``env``
    renders the per-run variables the worker needs to find its own manifest and
    results location.
    """

    image: str
    service_account: str
    machine_type: str = "g2-standard-4"
    boot_disk_type: str = "pd-balanced"
    boot_disk_gb: int = 100
    task_timeout_seconds: int = 3_600
    max_retry_count: int = 0
    mounts: tuple = ()
    arguments: tuple = ()
    results_prefix: str = "results/"

    def __post_init__(self):
        if "@sha256:" not in self.image:
            raise ValueError(f"image must be pinned by digest: {self.image!r}")
        if not self.service_account:
            raise ValueError("service_account is required")
        if self.max_retry_count < 0 or self.task_timeout_seconds <= 0:
            raise ValueError("retry count and task timeout must be non-negative/positive")
        if not self.arguments:
            raise ValueError("arguments must name the worker's manifest and launcher")
        for mount in self.mounts:
            if not isinstance(mount, Mount):
                raise ValueError(f"mounts must be Mount records: {mount!r}")

    def env(self, run_id, attempt):
        """Per-task variables; the run identity comes from the pinned spec."""
        return {
            "RUN_ID": run_id,
            "ATTEMPT": str(int(attempt)),
            "RESULT_PREFIX": self.results_prefix,
        }
