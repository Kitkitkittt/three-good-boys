"""Artifact storage seam: conditional create and generation-pinned manifests.

The in-memory store implements the same rules the GCS adapter (ticket 19) must:
never overwrite a differing object, pin each object's generation and checksum,
and treat changed content under a pinned name as a conflict.
"""
import dataclasses
import hashlib

from .errors import Conflict, IncompleteManifest, ManifestConflict
from .manifest import ManifestEntry


@dataclasses.dataclass(frozen=True)
class ObjectVersion:
    name: str
    generation: int
    content: bytes

    @property
    def checksum(self):
        return hashlib.sha256(self.content).hexdigest()


class InMemoryArtifactStore:
    """Test double for the GCS bucket; no credentials, no network."""

    def __init__(self):
        self._objects = {}  # name -> [ObjectVersion, ...]

    def head(self, name):
        versions = self._objects.get(name)
        return versions[-1] if versions else None

    def put_if_absent(self, name, content, if_generation_match=0):
        """Create only when the precondition holds; identical content reuses the object."""
        current = self.head(name)
        if current is not None:
            if current.content == content:
                return current
            raise Conflict(f"{name!r} already exists with different content")
        if if_generation_match is not None and if_generation_match != 0:
            raise Conflict(f"{name!r} does not exist, expected generation {if_generation_match}")
        version = ObjectVersion(name=name, generation=1, content=content)
        self._objects[name] = [version]
        return version

    def read(self, name, generation):
        for version in self._objects.get(name, ()):
            if version.generation == generation:
                return version.content
        raise Conflict(f"{name!r} has no generation {generation}")

    def pin(self, manifest, prefix=""):
        """Pin each required object's current generation; a pinned manifest is final."""
        for existing in manifest.entries:
            key = prefix + existing.name
            current = self.head(key)
            if current is None:
                raise IncompleteManifest(f"run {manifest.run_id} lost stored object {key!r}")
            if (current.generation, current.checksum) != (existing.generation, existing.checksum):
                raise ManifestConflict(
                    f"{key!r} moved from generation {existing.generation} to {current.generation}"
                )
        pinned = manifest
        for name in sorted(manifest.required - {entry.name for entry in manifest.entries}):
            key = prefix + name
            current = self.head(key)
            if current is None:
                raise IncompleteManifest(f"run {manifest.run_id} has no stored object {key!r}")
            pinned = pinned.add(
                ManifestEntry(
                    name=name,
                    generation=current.generation,
                    checksum=current.checksum,
                    size=len(current.content),
                )
            )
        return pinned.verify_complete()

    def verify(self, manifest, prefix=""):
        """Re-read every pinned generation and compare checksums."""
        for entry in manifest.entries:
            key = prefix + entry.name
            content = self.read(key, entry.generation)
            if hashlib.sha256(content).hexdigest() != entry.checksum:
                raise ManifestConflict(f"{key!r} generation {entry.generation} no longer matches its checksum")
        return manifest

    # Test hooks only; real adapters must not offer these.
    def replace_for_test(self, name, content):
        versions = self._objects.setdefault(name, [])
        versions.append(ObjectVersion(name=name, generation=len(versions) + 1, content=content))

    def drop_for_test(self, name):
        self._objects.pop(name, None)

    def generations_for_test(self, name):
        return [version.generation for version in self._objects.get(name, ())]
