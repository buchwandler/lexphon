from __future__ import annotations
# ruff: noqa: I001

import importlib.util
import sys
from pathlib import Path


_spec = importlib.util.spec_from_file_location(
    "validate_pronunciations", Path(__file__).parents[1] / "scripts" / "validate_pronunciations.py"
)
assert _spec and _spec.loader
_validation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _validation
_spec.loader.exec_module(_validation)


def test_levenshtein_distance_cases() -> None:
    assert _validation.pronunciation_distance("a", "a", broad=False) == _validation.DistanceResult(
        0, 0.0
    )
    assert _validation.pronunciation_distance("a", "i", broad=False).normalized == 1.0
    assert _validation.pronunciation_distance("ab", "a", broad=False) == _validation.DistanceResult(
        1, 0.5
    )
    assert _validation.pronunciation_distance("a", "ab", broad=False) == _validation.DistanceResult(
        1, 0.5
    )
    assert _validation.pronunciation_distance("", "", broad=False) == _validation.DistanceResult(
        0, 0.0
    )
    assert _validation.pronunciation_distance("", "a", broad=False) == _validation.DistanceResult(
        1, 1.0
    )


def test_distance_classification_boundaries() -> None:
    assert _validation.classify_distance(0.0) == "match"
    assert _validation.classify_distance(0.15) == "very_close"
    assert _validation.classify_distance(0.30) == "different"
    assert _validation.classify_distance(0.50) == "inspect"
    assert _validation.classify_distance(0.51) == "strong_disagreement"
