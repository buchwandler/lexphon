from __future__ import annotations

import pytest

from lexphon.alphabets import arpabet_to_ipa, to_ipa
from lexphon.errors import UnsupportedAlphabetError
from lexphon.profiles import LanguageProfile, ProfileRegistry


def test_arpabet_rejects_empty_value() -> None:
    with pytest.raises(UnsupportedAlphabetError, match="must contain phone tokens"):
        arpabet_to_ipa("")


def test_arpabet_rejects_invalid_token_syntax() -> None:
    with pytest.raises(UnsupportedAlphabetError, match="invalid ARPABET token"):
        arpabet_to_ipa("HH ???")


def test_arpabet_rejects_stress_on_consonant() -> None:
    with pytest.raises(UnsupportedAlphabetError, match="stress on ARPABET consonant"):
        arpabet_to_ipa("B1")


def test_arpabet_rejects_unsupported_phoneme() -> None:
    with pytest.raises(UnsupportedAlphabetError, match="unsupported ARPABET phoneme"):
        arpabet_to_ipa("ZZ")


def test_arpabet_uses_schwa_for_unstressed_er() -> None:
    assert arpabet_to_ipa("ER0") == "ɚ"


def test_arpabet_places_secondary_and_primary_stress() -> None:
    assert arpabet_to_ipa("HH EH2 L OW1") == "ˌhɛˈloʊ"


def test_to_ipa_rejects_empty_values_and_unsupported_encodings() -> None:
    with pytest.raises(UnsupportedAlphabetError, match="non-empty string"):
        to_ipa("", "ipa")
    with pytest.raises(UnsupportedAlphabetError, match="unsupported pronunciation encoding"):
        to_ipa("abc", "xsampa")


def test_profile_candidates_without_unicode_normalization() -> None:
    profile = LanguageProfile(
        language="de-DE",
        aliases=(),
        default_lexicons=(),
        case_candidates=("exact", "casefold", "normalized", "bogus"),
        unicode_normalization="none",
        apostrophe_normalization="ascii",
    )

    assert profile.candidates("Straße’S") == ("Straße'S", "strasse's")


def test_profile_registry_returns_generic_profile_for_unknown_language() -> None:
    profile = ProfileRegistry(()).resolve("xx_YY")

    assert profile.language == "xx_YY"
    assert profile.default_lexicons == ()
    assert profile.case_candidates == ("exact", "lower", "title")
