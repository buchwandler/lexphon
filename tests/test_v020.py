from __future__ import annotations

from pathlib import Path

import pytest

from lexphon import (
    BatchPronunciationProvider,
    DataStore,
    LexiconNotInstalledError,
    Phonemizer,
    PronunciationToken,
    PronunciationVariant,
    ProviderExecutionError,
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
    with Phonemizer("DE_DE", lexicons=[], fallback=provider) as engine:
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


def test_none_uses_profile_defaults_but_empty_lexicons_is_provider_only(tmp_path: Path) -> None:
    provider = BatchProvider()
    with Phonemizer(
        "de-DE",
        lexicons=[],
        store=DataStore(tmp_path / "provider-only"),
        fallback=provider,
    ) as engine:
        assert engine.lookup("missing") is not None

    with pytest.raises(LexiconNotInstalledError):
        Phonemizer("de-DE", store=DataStore(tmp_path / "profile-defaults"))


def test_direct_lookup_miss_is_none_without_provider() -> None:
    with Phonemizer("xx_YY") as engine:
        assert engine.lookup_lexicon("missing") is None
        assert engine.lookup("missing") is None
        assert engine.lookup_many(("one", "two")) == (None, None)
        assert engine.phonemize_tokens("one two").unknown_tokens[0].source == "unknown"


def test_lookup_many_does_not_construct_fallback_when_all_tokens_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def lexical(_self: Phonemizer, token: str, *, tag: str | None = None) -> PronunciationToken:
        return PronunciationToken(
            text=token,
            source="lexicon",
            variants=(PronunciationVariant(pronunciation="known", source_pronunciation="known"),),
            lexicon_id="fixture",
            source_encoding="ipa",
        )

    monkeypatch.setattr(Phonemizer, "lookup_lexicon", lexical)
    monkeypatch.setattr(
        "lexphon.engine.create_provider",
        lambda _name: pytest.fail("fallback provider must not be constructed"),
    )
    with Phonemizer("xx-YY", lexicons=[], fallback="goruut") as engine:
        results = engine.lookup_many(("one", "two"))
    assert [result.text for result in results if result is not None] == ["one", "two"]


def test_lookup_many_provider_receives_only_lexicon_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = BatchProvider()

    def lexical(
        _self: Phonemizer, token: str, *, tag: str | None = None
    ) -> PronunciationToken | None:
        if token == "known":
            return PronunciationToken(
                text=token,
                source="lexicon",
                variants=(
                    PronunciationVariant(pronunciation="known", source_pronunciation="known"),
                ),
                lexicon_id="fixture",
                source_encoding="ipa",
            )
        return None

    monkeypatch.setattr(Phonemizer, "lookup_lexicon", lexical)
    with Phonemizer("xx-YY", lexicons=[], fallback=provider) as engine:
        results = engine.lookup_many(("known", "missing"))
    assert results[0] is not None and results[0].source == "lexicon"
    assert results[1] is not None and results[1].source == "provider"
    assert provider.batch_calls == [("missing",)]


@pytest.mark.parametrize("invalid", ["ab", object()])
def test_invalid_batch_top_level_is_a_provider_output_error(invalid: object) -> None:
    class InvalidBatchProvider(BatchProvider):
        def phonemize_many(self, texts: tuple[str, ...], language: str) -> object:
            return invalid

    with (
        Phonemizer("xx-YY", lexicons=[], fallback=InvalidBatchProvider()) as engine,
        pytest.raises(ProviderOutputError, match="invalid batch output"),
    ):
        engine.lookup_many(("one", "two"))


def test_malformed_batch_element_is_a_provider_output_error() -> None:
    class MalformedBatchProvider(BatchProvider):
        def phonemize_many(self, texts: tuple[str, ...], language: str) -> tuple[object, ...]:
            return ("valid", 3)

    with (
        Phonemizer("xx-YY", lexicons=[], fallback=MalformedBatchProvider()) as engine,
        pytest.raises(ProviderOutputError, match="malformed pronunciation output"),
    ):
        engine.lookup_many(("one", "two"))


def test_batch_provider_failure_is_a_provider_execution_error() -> None:
    class FailingBatchProvider(BatchProvider):
        def phonemize_many(self, texts: tuple[str, ...], language: str) -> tuple[str, ...]:
            raise RuntimeError("boom")

    with (
        Phonemizer("xx-YY", lexicons=[], fallback=FailingBatchProvider()) as engine,
        pytest.raises(ProviderExecutionError, match="batch execution failed"),
    ):
        engine.lookup_many(("one", "two"))


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
    with Phonemizer("de-DE", lexicons=[], fallback=provider) as engine:
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
