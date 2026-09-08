"""Sketch of the Lexphon to KokoroG2P integration boundary.

Lexphon owns generic provider cleanup and returns clean IPA with structured
provenance. The downstream application owns IPA-to-model conversion.
"""

from lexphon import Phonemizer


def kokoro_word_phonemes(word: str, *, language: str = "de-DE") -> str:
    with Phonemizer(
        language,
        lexicons=["de-de:gold"],
        fallback="espeak",
    ) as engine:
        lexical = engine.lookup_lexicon(word)
        actual = engine.lookup(word)

    if actual is not None:
        # return kokorog2p.convert_ipa_to_kokoro(actual.pronunciation)
        return actual.pronunciation or ""
    if lexical is None:
        raise LookupError(f"Lexphon miss for {word!r}")
    raise LookupError(f"Lexphon returned no pronunciation for {word!r}")
