from __future__ import annotations

import pytest

from lexphon.errors import ProviderOutputError
from lexphon.models import PhonemizationResult, PronunciationToken, PronunciationVariant


def test_structured_variants_are_authoritative() -> None:
    variant = PronunciationVariant("noʊn", "raw-noʊn")
    token = PronunciationToken("known", "provider", variants=(variant,))
    assert token.pronunciation == "noʊn"
    assert token.source_pronunciation == "raw-noʊn"
    assert token.variants == (variant,)
    assert token.known


def test_unknown_token_has_no_variants() -> None:
    token = PronunciationToken("mystery", "unknown")
    assert token.pronunciation is None
    assert token.source_pronunciation is None
    assert not token.known


def test_provider_output_error_is_a_lexphon_error() -> None:
    assert issubclass(ProviderOutputError, Exception)


def _result() -> tuple[PhonemizationResult, PronunciationToken]:
    punct = PronunciationToken(",", "literal", punctuation=True)
    unknown = PronunciationToken("mystery", "unknown")
    known = PronunciationToken(
        "known",
        "lexicon",
        variants=(PronunciationVariant("noʊn", "noʊn"),),
    )
    final_punct = PronunciationToken("!", "literal", punctuation=True)
    return (
        PhonemizationResult(
            text=", mystery known!",
            language="en-us",
            tokens=(punct, unknown, known, final_punct),
        ),
        unknown,
    )


def test_unknown_tokens_ignores_punctuation() -> None:
    result, unknown = _result()
    assert result.unknown_tokens == (unknown,)


def test_render_rejects_invalid_policies() -> None:
    result, _ = _result()
    with pytest.raises(ValueError, match="unknown must"):
        result.render(unknown="wat")
    with pytest.raises(ValueError, match="punctuation must"):
        result.render(punctuation="wat")


def test_render_keeps_unknowns_and_punctuation() -> None:
    result, _ = _result()
    assert result.render(unknown="keep", punctuation="keep") == ", mystery noʊn!"


def test_render_skips_unknowns_and_drops_punctuation() -> None:
    result, _ = _result()
    assert result.render(unknown="skip", punctuation="drop") == "noʊn"
