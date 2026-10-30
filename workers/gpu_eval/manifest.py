"""Run manifest check-in for the Batch worker (stdlib only).

The manifest is a JSON file whose identity paths are relative to its own
directory. It names the sample ids in order, the input seed checksums and
optional already-fetched input objects (cache trees, audio, ...). Anything
the adapter does not recognise is refused so a newer producer cannot be
silently half-read.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """The run manifest is malformed, unsafe or incomplete."""


def sha_file(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def is_sha256(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


@dataclass(frozen=True)
class Manifest:
    path: Path
    ids: tuple
    files: dict      # run-relative posix path -> sha256
    seeds: dict      # logical input name -> sha256
    checksums: dict  # service object uri -> sha256, when supplied

    @property
    def root(self):
        return self.path.parent

    def file(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ManifestError(f"manifest path escapes its directory: {name}")
        return path


def _from_runner(document):
    """Normalise the runner's `manifest_for(...)` identity document, when given."""
    files, seeds = {}, {}
    for name in ("llm", "asr", "organizer_library"):
        for relative, digest in (document.get(name) or {}).items():
            files[f"{name}/{relative}"] = is_sha256(digest) and digest or None
    for name, key in (("config", "source_sha256"), ("model", "catalog_sha256"),
                      ("audio", "input_sha256")):
        digest = document.get(key)
        if is_sha256(digest):
            seeds[name] = digest
    ids = [row for row in str(document.get("sample_ids", "")).split(",") if row]
    for name, value in files.items():
        if value is None:
            raise ManifestError(f"runner manifest checksum for {name!r} is not sha256")
    return {"ids": ids, "files": files, "seeds": seeds}


def read_manifest(path):
    """Parse and check a run manifest; every listed path must exist inside its root."""
    path = Path(path).resolve()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"cannot read run manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise ManifestError("run manifest must be a JSON object")
    if "source_sha256" in document:      # the runner's own manifest_for(...) output
        document = _from_runner(document)
    unknown = set(document) - {"ids", "files", "seeds", "checksums"}
    if unknown:
        raise ManifestError(f"unknown manifest fields: {sorted(unknown)}")
    ids = document.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) and i for i in ids):
        raise ManifestError("manifest ids must be a list of non-empty strings")
    if len(ids) != len(set(ids)):
        raise ManifestError("manifest ids must be unique sample ids")
    seeds = document.get("seeds")
    if not isinstance(seeds, dict):
        raise ManifestError("manifest seeds must be an object")
    for name in ("config", "model", "audio"):
        if not is_sha256(seeds.get(name)):
            raise ManifestError(f"manifest seeds are missing {name!r}")
    files = document.get("files")
    if not isinstance(files, dict):
        raise ManifestError("manifest files must be an object")
    root = path.parent
    for relative in files:
        target = (root / relative).resolve()
        if not isinstance(relative, str) or not target.is_relative_to(root):
            raise ManifestError(f"manifest path escapes its directory: {relative}")
        if not target.is_file():
            raise ManifestError(f"manifest lists a missing file: {relative}")
    for name, digest in {**seeds, **files}.items():
        if not is_sha256(digest):
            raise ManifestError(f"manifest checksum for {name!r} is not sha256")
    checksums = document.get("checksums") or {}
    if not isinstance(checksums, dict) or not all(
            uri.startswith("gs://") and is_sha256(digest) for uri, digest in checksums.items()):
        raise ManifestError("manifest checksums must map gs:// objects to sha256 digests")
    return Manifest(path=path, ids=tuple(ids), files=dict(files), seeds=dict(seeds),
                    checksums=dict(checksums))


# ponytail: files are re-hashed on every run; cache digests in the manifest only
# when a large audio tree makes this check-in cost measurable.
def verify_files(manifest):
    """Reject any listed input whose bytes no longer match the manifest."""
    for relative, expected in manifest.files.items():
        if sha_file(manifest.file(relative)) != expected:
            raise ManifestError(f"run input changed: {relative}")
    return manifest
