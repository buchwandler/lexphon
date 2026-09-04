from __future__ import annotations

from types import SimpleNamespace

import pytest

from lexphon import fallback
from lexphon.errors import LexphonError, UnknownWordError
from lexphon.models import PhonemizationResult, PronunciationToken


def test_espeak_fallback_requires_an_installed_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fallback.shutil, "which", lambda name: None)

    with pytest.raises(LexphonError, match="not installed"):
        fallback.EspeakFallback()


def test_espeak_fallback_uses_explicit_executable() -> None:
    assert fallback.EspeakFallback("/fake/espeak").executable == "/fake/espeak"


def test_espeak_fallback_returns_none_for_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fallback.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="ignored"),
    )

    assert fallback.EspeakFallback("/fake/espeak").phonemize("Hallo", "de_DE") is None


def test_espeak_fallback_normalizes_voice_and_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0, stdout="  haː loʊ  \n")

    monkeypatch.setattr(fallback.subprocess, "run", run)

    assert fallback.EspeakFallback("/fake/espeak").phonemize("Hallo", "de_DE") == "haː loʊ"
    assert calls == [("/fake/espeak", "-q", "--ipa=3", "-v", "de-de", "Hallo")]


def test_espeak_fallback_returns_none_for_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fallback.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=" \n"),
    )

    assert fallback.EspeakFallback("/fake/espeak").phonemize("Hallo", "de_DE") is None


def _result() -> tuple[PhonemizationResult, PronunciationToken]:
    punct = PronunciationToken(",", None, "literal", punctuation=True)
    unknown = PronunciationToken("mystery", None, "unknown")
    known = PronunciationToken("known", "noʊn", "lexicon")
    final_punct = PronunciationToken("!", None, "literal", punctuation=True)
    return (
        PhonemizationResult(
            text=", mystery known!",
            language="en-US",
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


def test_render_errors_on_unknown_words() -> None:
    result, _ = _result()

    with pytest.raises(UnknownWordError, match="mystery"):
        result.render()


def test_render_keeps_unknowns_and_punctuation() -> None:
    result, _ = _result()

    assert result.render(unknown="keep", punctuation="keep") == ", mystery noʊn!"


def test_render_skips_unknowns_and_drops_punctuation() -> None:
    result, _ = _result()

    assert result.render(unknown="skip", punctuation="drop") == "noʊn"
