"""Sketch of the intended KokoroG2P integration boundary.

This example intentionally does not import KokoroG2P: Lexphon returns IPA and
keeps unknown tokens explicit; the downstream application owns IPA->model
conversion and fallback policy.
"""

from lexphon import DataStore, Phonemizer


def kokoro_word_phonemes(word: str, *, lexicon_id: str, language: str = "de-DE") -> str:
    store = DataStore()
    with Phonemizer(language, lexicons=[lexicon_id], store=store, fallback=None) as lexphon:
        token = lexphon.lookup(word)

    if token.pronunciation is not None:
        # return kokorog2p.convert_ipa_to_kokoro(token.pronunciation)
        return token.pronunciation

    # KokoroG2P should perform its own eSpeak fallback here, then convert that IPA
    # into the model-compatible phoneme inventory.
    raise LookupError(f"Lexphon miss for {word!r}; invoke application fallback")
