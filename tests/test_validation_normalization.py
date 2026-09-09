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


def test_nfc_equivalent_ipa_is_equal() -> None:
    assert _validation.normalize_exact_ipa("a\u0308") == _validation.normalize_exact_ipa("ä")


def test_stress_is_preserved_exactly_but_ignored_broadly() -> None:
    assert _validation.normalize_exact_ipa("ˈhaus") != _validation.normalize_exact_ipa("haus")
    assert _validation.normalize_broad_ipa("ˈhaus") == _validation.normalize_broad_ipa("haus")
    assert _validation.pronunciation_distance("ˈhaus", "haus", broad=False).normalized > 0
    assert _validation.pronunciation_distance("ˈhaus", "haus", broad=True).normalized == 0


def test_tie_bar_is_a_single_exact_unit_and_harmless_broadly() -> None:
    assert _validation.normalize_exact_ipa("t͡ʃ") == ("t͡ʃ",)
    assert _validation.normalize_broad_ipa("t͡ʃ") == _validation.normalize_broad_ipa("tʃ")


def test_segmental_and_length_differences_remain() -> None:
    assert _validation.normalize_broad_ipa("i") != _validation.normalize_broad_ipa("e")
    assert _validation.normalize_broad_ipa("t") != _validation.normalize_broad_ipa("d")
    assert _validation.normalize_broad_ipa("a") != _validation.normalize_broad_ipa("aː")
    assert _validation.normalize_broad_ipa("a") != _validation.normalize_broad_ipa("ã")
