from __future__ import annotations

import pytest

from lexphon import (
    BatchPronunciationProvider,
    Phonemizer,
    PronunciationVariant,
    ProviderOutputError,
)


class BatchProvider:
    name = "fake"
    source_encoding = "ipa"

    def __init__(self) -> None:
        self.scalar_calls: list[str] = []
        self.batch_calls: list[tuple[str, ...]] = []

    def phonemize(self, text: str, language: str) -> str:
        self.scalar_calls.append(text)
        return f"({language}){text}"

    def phonemize_many(self, texts: tuple[str, ...], language: str) -> tuple[str, ...]:
        self.batch_calls.append(texts)
        return tuple(f"({language}){text}" for text in texts)


def test_batch_provider_protocol_is_runtime_checkable() -> None:
    assert isinstance(BatchProvider(), BatchPronunciationProvider)


def test_lookup_and_text_api_use_one_provider_batch_call() -> None:
    provider = BatchProvider()
    with Phonemizer("DE_DE", fallback=provider) as engine:
        assert engine.lookup("missing") is not None
        provider.batch_calls.clear()
        provider.scalar_calls.clear()
        result = engine.phonemize_tokens("one, two")

    assert provider.batch_calls == [("one", "two")]
    assert provider.scalar_calls == []
    assert [token.text for token in result.tokens] == ["one", ",", "two"]
    assert [token.pronunciation for token in result.tokens] == ["one", None, "two"]
    assert result.tokens[0].requested_language == "de-de"
    assert result.tokens[0].source == "provider"


def test_direct_lookup_miss_is_none_without_provider() -> None:
    with Phonemizer("xx_YY") as engine:
        assert engine.lookup_lexicon("missing") is None
        assert engine.lookup("missing") is None
        assert engine.lookup_many(("one", "two")) == (None, None)
        assert engine.phonemize_tokens("one two").unknown_tokens[0].source == "unknown"


def test_bad_batch_cardinality_is_a_provider_output_error() -> None:
    class BadBatchProvider(BatchProvider):
        def phonemize_many(self, texts: tuple[str, ...], language: str) -> tuple[str, ...]:
            return ("one",)

    with (
        Phonemizer("xx-YY", fallback=BadBatchProvider()) as engine,
        pytest.raises(ProviderOutputError, match="returned 1 results for 2 inputs"),
    ):
        engine.lookup_many(("one", "two"))


def test_provider_output_is_normalized_at_engine_boundary() -> None:
    provider = BatchProvider()
    provider.phonemize = lambda text, language: "(en)f\u02c8Il(de)"  # type: ignore[method-assign]
    with Phonemizer("de-DE", fallback=provider) as engine:
        token = engine.lookup("File")

    assert token is not None
    assert token.variants == (
        PronunciationVariant(
            pronunciation="fˈIl",
            source_pronunciation="(en)fˈIl(de)",
            language_markers=token.language_markers,
        ),
    )
    assert token.source_pronunciation == "(en)fˈIl(de)"
