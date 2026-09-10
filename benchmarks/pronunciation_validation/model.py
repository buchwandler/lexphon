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
