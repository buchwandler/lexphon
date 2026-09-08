from __future__ import annotations

import pytest

from lexphon import PronunciationLanguageMarker, PronunciationVariant
from lexphon.pronunciation import parse_pronunciation_controls, strip_language_controls


@pytest.mark.parametrize(
    ("source", "clean", "markers"),
    [
        ("(en)fˈIl(de)", "fˈIl", (("en", 0), ("de", 4))),
        ("(fr)bɔ̃(de)", "bɔ̃", (("fr", 0), ("de", 3))),
        ("(pt-BR)foo(de-DE)", "foo", (("pt-br", 0), ("de-de", 3))),
        ("(en-US)hello", "hello", (("en-us", 0),)),
        ("hello", "hello", ()),
        ("(ə)", "(ə)", ()),
        ("(t)", "(t)", ()),
        ("(foo bar)", "(foo bar)", ()),
        ("(1)", "(1)", ()),
    ],
)
def test_parse_provider_controls(
    source: str, clean: str, markers: tuple[tuple[str, int], ...]
) -> None:
    result = parse_pronunciation_controls(source)

    assert result == PronunciationVariant(
        pronunciation=clean,
        source_pronunciation=source,
        language_markers=tuple(PronunciationLanguageMarker(*marker) for marker in markers),
    )


def test_controls_accept_hidden_unicode_format_characters() -> None:
    source = "\u2068(en)\u2069fˈIl\u2068(de)\u2069"

    clean, markers = strip_language_controls(source)

    assert clean == "fˈIl"
    assert markers == (
        PronunciationLanguageMarker("en", 0),
        PronunciationLanguageMarker("de", 4),
    )


def test_unrelated_format_characters_are_preserved() -> None:
    source = "a\u200db"

    assert parse_pronunciation_controls(source).pronunciation == source


def test_marker_offsets_follow_nfc_normalization() -> None:
    result = parse_pronunciation_controls("e\u0301(en)a")

    assert result.pronunciation == "éa"
    assert result.language_markers == (PronunciationLanguageMarker("en", 1),)
