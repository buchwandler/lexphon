from __future__ import annotations

import unicodedata

import pytest

from lexphon import Phonemizer, PronunciationToken, PronunciationVariant
from lexphon.tokenizer import tokenize


def test_nfc_and_nfd_words_remain_single_tokens() -> None:
    nfc = "Café"
    nfd = unicodedata.normalize("NFD", nfc)

    assert tokenize(nfc) == ((nfc, False),)
    assert tokenize(nfd) == ((nfd, False),)


def test_tokenizer_preserves_internal_apostrophes_and_hyphens() -> None:
    assert tokenize("l'amour rock-n-roll") == (
        ("l'amour", False),
        ("rock-n-roll", False),
    )
    assert tokenize("word-") == (("word", False), ("-", True))


def test_tokenizer_keeps_punctuation_classification() -> None:
    assert tokenize("Hello, world!") == (
        ("Hello", False),
        (",", True),
        ("world", False),
        ("!", True),
    )


def test_nfc_and_nfd_lookup_results_are_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def lookup(
        _self: Phonemizer, token: str, *, tag: str | None = None
    ) -> PronunciationToken | None:
        if unicodedata.normalize("NFC", token) != "Café":
            return None
        return PronunciationToken(
            text=token,
            source="lexicon",
            variants=(PronunciationVariant(pronunciation="kafe", source_pronunciation="kafe"),),
            lexicon_id="fixture",
            source_encoding="ipa",
        )

    monkeypatch.setattr(Phonemizer, "lookup_lexicon", lookup)
    nfc = "Café"
    nfd = unicodedata.normalize("NFD", nfc)
    with Phonemizer("xx-YY", lexicons=[]) as engine:
        nfc_result = engine.phonemize_tokens(nfc)
        nfd_result = engine.phonemize_tokens(nfd)

    assert nfc_result.tokens[0].pronunciation == nfd_result.tokens[0].pronunciation == "kafe"
    assert nfd_result.tokens[0].text == nfd
