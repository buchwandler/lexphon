from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from lexphon import BatchPronunciationProvider, EspeakProvider, Phonemizer, PronunciationToken
from lexphon.errors import ProviderOutputError, ProviderUnavailableError
from lexphon.models import PronunciationVariant


class FakeRuntime:
    def __init__(self, outputs: list[object] | None = None) -> None:
        self.info = SimpleNamespace(
            executable="/fake/espeak", version="1.2.3", implementation="cli"
        )
        self.outputs = outputs
        self.batch_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def phonemize(self, text: str, **_kwargs: object) -> str:
        return f"{text} ipa"

    def phonemize_many(self, texts: tuple[str, ...], **kwargs: object) -> list[object]:
        self.batch_calls.append((texts, kwargs))
        return self.outputs if self.outputs is not None else [f"{text} ipa" for text in texts]

    def close(self) -> None:
        pass


def _provider(runtime: FakeRuntime | None = None) -> EspeakProvider:
    return EspeakProvider(runtime=runtime or FakeRuntime())


def _lexical_result(token: str) -> PronunciationToken:
    return PronunciationToken(
        text=token,
        source="lexicon",
        variants=(PronunciationVariant(pronunciation="known", source_pronunciation="known"),),
        lexicon_id="fixture",
        source_encoding="ipa",
    )


def test_espeak_provider_is_batch_provider() -> None:
    assert isinstance(_provider(), BatchPronunciationProvider)


def test_batch_uses_one_runtime_call_and_preserves_order() -> None:
    runtime = FakeRuntime()
    provider = _provider(runtime)

    result = provider.phonemize_many(("first", "second", "third"), "en-US")

    assert result == ("first ipa", "second ipa", "third ipa")
    assert runtime.batch_calls == [
        (
            ("first", "second", "third"),
            {"voice": "en-us", "use_tie": True, "tie_char": "\u200d"},
        )
    ]


def test_engine_sends_only_lexicon_misses_to_provider_batch() -> None:
    runtime = FakeRuntime()
    provider = _provider(runtime)

    def lookup_lexicon(
        _self: Phonemizer, token: str, *, tag: str | None = None
    ) -> PronunciationToken | None:
        return _lexical_result(token) if token in {"known", "known-two"} else None

    original = Phonemizer.lookup_lexicon
    Phonemizer.lookup_lexicon = lookup_lexicon
    try:
        with Phonemizer("de-DE", lexicons=[], fallback=provider) as engine:
            results = engine.lookup_many(("known", "missing-a", "known-two", "missing-b"))
    finally:
        Phonemizer.lookup_lexicon = original

    assert runtime.batch_calls[0][0] == ("missing-a", "missing-b")
    assert [result.source if result else None for result in results] == [
        "lexicon",
        "provider",
        "lexicon",
        "provider",
    ]


def test_all_lexicon_hits_do_not_invoke_provider_batch() -> None:
    runtime = FakeRuntime()
    provider = _provider(runtime)

    def lookup_lexicon(
        _self: Phonemizer, _token: str, *, tag: str | None = None
    ) -> PronunciationToken:
        return _lexical_result("known")

    original = Phonemizer.lookup_lexicon
    Phonemizer.lookup_lexicon = lookup_lexicon
    try:
        with Phonemizer("de-DE", lexicons=[], fallback=provider) as engine:
            results = engine.lookup_many(tuple(f"known-{index}" for index in range(10)))
    finally:
        Phonemizer.lookup_lexicon = original

    assert runtime.batch_calls == []
    assert len(results) == 10
    assert all(result is not None and result.source == "lexicon" for result in results)


def test_batch_cardinality_is_validated_at_provider_boundary() -> None:
    provider = _provider(FakeRuntime(outputs=["one"]))

    with pytest.raises(ProviderOutputError, match=r"returned 1 results for 2 inputs"):
        provider.phonemize_many(("Haus", "Welt"), "de-DE")


def test_empty_batch_does_not_invoke_runtime() -> None:
    runtime = FakeRuntime()
    provider = _provider(runtime)

    assert provider.phonemize_many((), "de-DE") == ()
    assert runtime.batch_calls == []


@pytest.mark.skipif(
    shutil.which("espeak-ng") is None and shutil.which("espeak") is None,
    reason="eSpeak CLI is not installed",
)
def test_cli_provider_matches_legacy_ipa3_output() -> None:
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    assert executable is not None
    corpus = (
        ("de-DE", "Haus"),
        ("de-DE", "Deutsch"),
        ("en-US", "hello"),
        ("en-US", "church"),
        ("fr-FR", "bonjour"),
    )
    provider = EspeakProvider(mode="cli", executable=executable)
    try:
        for language, text in corpus:
            legacy = subprocess.run(
                [executable, "-q", "--ipa=3", "-v", language.casefold(), text],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            assert provider.phonemize(text, language) == legacy
    finally:
        provider.close()


def test_auto_and_native_match_cli_when_native_is_available() -> None:
    executable = shutil.which("espeak-ng") or shutil.which("espeak")
    if executable is None:
        pytest.skip("eSpeak CLI is not installed")
    try:
        cli = EspeakProvider(mode="cli", executable=executable)
        auto = EspeakProvider(mode="auto")
    except ProviderUnavailableError as error:
        pytest.skip(f"eSpeak runtime unavailable: {error}")
    try:
        if getattr(auto.runtime_info, "implementation", None) != "native":
            pytest.skip("native eSpeak runtime is not available")
        for language, text in (("de-DE", "Haus"), ("en-GB", "hello"), ("fr-FR", "bonjour")):
            assert auto.phonemize(text, language) == cli.phonemize(text, language)
    finally:
        cli.close()
        auto.close()
