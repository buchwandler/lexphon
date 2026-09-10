"""Catalog-driven pronunciation validation benchmarks."""

from .distance import (
    classify_distance,
    levenshtein,
    normalize_broad_ipa,
    normalize_exact_ipa,
    pronunciation_distance,
)
from .model import BenchmarkPaths, BenchmarkSpec, DistanceResult, RankedWord, ReferenceResult
from .runner import main_for, run_spec

__all__ = [
    "BenchmarkPaths",
    "BenchmarkSpec",
    "DistanceResult",
    "RankedWord",
    "ReferenceResult",
    "classify_distance",
    "levenshtein",
    "main_for",
    "normalize_broad_ipa",
    "normalize_exact_ipa",
    "pronunciation_distance",
    "run_spec",
]
