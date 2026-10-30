"""Generation-pinned result manifest."""
import dataclasses
import re

from .errors import IncompleteManifest, ManifestConflict

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclasses.dataclass(frozen=True)
class ManifestEntry:
    """One committed object: name, GCS generation and content checksum."""

    name: str
    generation: int
    checksum: str
    size: int = None

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or self.name.startswith("/") or ".." in self.name.split("/"):
            raise ValueError(f"illegal object name: {self.name!r}")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation < 1:
            raise ValueError("generation must be a pinned positive int")
        if not isinstance(self.checksum, str) or not _HEX64.match(self.checksum):
            raise ValueError("checksum must be lowercase sha256 hex")
        if self.size is not None and (isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0):
            raise ValueError("size must be a non-negative int when given")


@dataclasses.dataclass(frozen=True)
class ResultManifest:
    run_id: str
    required: frozenset
    entries: tuple

    @classmethod
    def create(cls, run_id, required):
        required = frozenset(required)
        if not required:
            raise ValueError("a manifest needs at least one required object")
        for name in required:
            ManifestEntry(name=name, generation=1, checksum="0" * 64)  # validates the name
        return cls(run_id=run_id, required=required, entries=())

    def add(self, entry):
        """Pin one object. Same entry is idempotent; different content conflicts."""
        if entry.name not in self.required:
            raise IncompleteManifest(f"object {entry.name!r} is not required by run {self.run_id}")
        for existing in self.entries:
            if existing.name == entry.name:
                if existing == entry:
                    return self
                raise ManifestConflict(
                    f"object {entry.name!r} already pinned at generation {existing.generation}"
                )
        entries = tuple(sorted(self.entries + (entry,), key=lambda item: item.name))
        return dataclasses.replace(self, entries=entries)

    def missing(self):
        return tuple(sorted(self.required - {entry.name for entry in self.entries}))

    @property
    def is_complete(self):
        return len(self.entries) == len(self.required) and not self.missing()

    def verify_complete(self):
        missing = self.missing()
        if missing:
            raise IncompleteManifest(f"run {self.run_id} is missing {list(missing)}")
        return self

    def verify_for(self, run_id):
        if run_id != self.run_id:
            raise IncompleteManifest(f"manifest belongs to run {self.run_id!r}, not {run_id!r}")
        return self.verify_complete()

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "required": sorted(self.required),
            "entries": [dataclasses.asdict(entry) for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, payload):
        document = cls.create(payload["run_id"], payload["required"])
        for raw in payload["entries"]:
            document = document.add(ManifestEntry(**raw))
        return document
