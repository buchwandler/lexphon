from __future__ import annotations

import pytest

from lexphon.alphabets import arpabet_to_ipa, normalize_pronunciation, to_ipa
from lexphon.errors import UnsupportedAlphabetError
from lexphon.models import PronunciationLanguageMarker
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


def test_ipa_language_markers_are_removed_from_public_pronunciation() -> None:
    result = normalize_pronunciation("(en)dˈaʊnləʊdən(de)", "ipa")

    assert result.pronunciation == "dˈaʊnləʊdən"
    assert result.source_pronunciation == "(en)dˈaʊnləʊdən(de)"
    assert tuple(marker.language for marker in result.language_markers) == ("en", "de")
    assert result.language_markers[0].ipa_offset == 0
    assert result.language_markers[1].ipa_offset == len(result.pronunciation)


def test_ipa_language_markers_normalize_locale_spelling() -> None:
    result = normalize_pronunciation("(EN_us)demo", "ipa")

    assert result.pronunciation == "demo"
    assert result.language_markers == (PronunciationLanguageMarker("en-us", 0),)


@pytest.mark.parametrize("value", ["(ə)abc", "(t)abc", "(optional)abc", "(foo bar)abc"])
def test_non_language_parentheses_are_not_silently_stripped(value: str) -> None:
    result = normalize_pronunciation(value, "ipa")

    assert result.pronunciation == value
    assert result.language_markers == ()


def test_to_ipa_removes_ipa_language_markers() -> None:
    assert to_ipa("(en)dˈaʊnləʊdən(de)", "ipa") == "dˈaʊnləʊdən"


def test_ipa_marker_offsets_use_nfc_normalized_segments() -> None:
    result = normalize_pronunciation("e\u0301(en)a", "ipa")

    assert result.pronunciation == "éa"
    assert result.language_markers == (PronunciationLanguageMarker("en", 1),)


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
