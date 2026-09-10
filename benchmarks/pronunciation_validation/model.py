"""Data models shared by pronunciation benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RankedWord:
    rank: int
    word: str


@dataclass(frozen=True, slots=True)
class DistanceResult:
    edits: int
    normalized: float


@dataclass(frozen=True, slots=True)
class PhoneticProvenance:
    status: str
    requested_language: str
    library: str | None = None
    library_version: str | None = None
    metric: str | None = None
    metric_version: str | None = None
    profile: str | None = None
    profile_version: str | None = None
    backend: str | None = None
    backend_version: str | None = None
    feature_set: str | None = None
    stress_policy: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PhoneticVariantResult:
    index: int
    status: str
    distance: float | None = None
    raw_cost: float | None = None
    denominator: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "status": self.status,
            "distance": self.distance,
            "raw_cost": self.raw_cost,
            "denominator": self.denominator,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ReferenceResult:
    status: str
    ipa: str | None = None
    source_pronunciation: str | None = None
    error: str | None = None

    provider: str | None = None
    source_encoding: str | None = None
    version: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    lexicon_id: str
    word_list_key: str | None = None
    reference_name: str = "espeak"
    reference_language: str | None = None
    report_threshold: float = 0.30
    strong_threshold: float = 0.50
    ignore_stress: bool = False


@dataclass(frozen=True, slots=True)
class WordListSpec:
    id: str
    language: str
    url: str
    revision: str | None
    format: str
    license_note: str | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkPaths:
    root: Path
    wordlists: Path
    reports: Path
    data: Path

    @classmethod
    def default(cls) -> BenchmarkPaths:
        root = Path(__file__).resolve().parent
        return cls(root, root / "wordlists", root / "reports", root / "data")


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    name: str
    source_encoding: str
    version: str | None
    language: str
    relationship: str


@dataclass(frozen=True, slots=True)
class WordListResult:
    words: tuple[RankedWord, ...]
    spec: WordListSpec
    source_path: Path
    download_sha256: str | None
    ranked_sha256: str
    retrieved_at: str | None
    rejected_rows: int = 0
    rejected_phrases: int = 0


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    status: str
    summary: dict[str, Any]
    rows: tuple[dict[str, Any], ...] = ()
