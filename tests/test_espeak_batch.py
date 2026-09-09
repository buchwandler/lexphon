from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace
from typing import Any

import pytest

from lexphon import (
    BatchPronunciationProvider,
    EspeakProvider,
    Phonemizer,
    PronunciationToken,
    PronunciationVariant,
    ProviderExecutionError,
    ProviderOutputError,
)


def _completed(stdout: str = "", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout)


def _lexical_result(token: str) -> PronunciationToken:
    return PronunciationToken(
        text=token,
        source="lexicon",
        variants=(PronunciationVariant(pronunciation="known", source_pronunciation="known"),),
        lexicon_id="fixture",
        source_encoding="ipa",
    )


def test_espeak_provider_is_batch_provider() -> None:
    provider = EspeakProvider(executable="/fake/espeak-ng")

    assert isinstance(provider, BatchPronunciationProvider)


def test_batch_uses_one_subprocess_and_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append((command, kwargs))
        return _completed("h...\nv...\nd...\n")

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)
    provider = EspeakProvider(executable="/fake/espeak-ng")

    result = provider.phonemize_many(("Haus", "Welt", "Datei"), "de-DE")

    assert result == ("h...", "v...", "d...")
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == ["/fake/espeak-ng", "-q", "--ipa=3", "-v", "de-de"]
    assert kwargs["input"] == "Haus\nWelt\nDatei\n"
    assert all(text not in command for text in ("Haus", "Welt", "Datei"))


def test_batch_preserves_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: _completed("A\nB\nC\n"),
    )

    result = EspeakProvider("/fake/espeak").phonemize_many(
        ("first", "second", "third"), "en-US"
    )

    assert result == ("A", "B", "C")


def test_batch_preserves_empty_input_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return _completed("Haus output\nWelt output\n")

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)

    result = EspeakProvider("/fake/espeak").phonemize_many(("", "Haus", " ", "Welt"), "de-DE")

    assert result == (None, "Haus output", None, "Welt output")
    assert len(calls) == 1
    assert calls[0]["input"] == "Haus\nWelt\n"


def test_batch_all_empty_does_not_run_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    run = pytest.MonkeyPatch()
    run.setattr("lexphon.providers.subprocess.run", lambda: pytest.fail("must not run"))
    try:
        assert EspeakProvider("/fake/espeak").phonemize_many(("", " ", ""), "de-DE") == (
            None,
            None,
            None,
        )
    finally:
        run.undo()


@pytest.mark.parametrize("value", ["Haus\nWelt", "Haus\rWelt"])
def test_batch_rejects_embedded_line_breaks(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: pytest.fail("must not run"),
    )

    with pytest.raises(ProviderExecutionError, match="must not contain line breaks"):
        EspeakProvider("/fake/espeak").phonemize_many((value,), "de-DE")



def test_batch_rejects_nonzero_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: _completed("partial\n", returncode=1),
    )

    with pytest.raises(ProviderExecutionError, match="status 1"):
        EspeakProvider("/fake/espeak").phonemize_many(("Haus",), "de-DE")


@pytest.mark.parametrize("error", [OSError("missing"), subprocess.SubprocessError("failed")])
def test_batch_wraps_process_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
        raise error

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)

    with pytest.raises(ProviderExecutionError, match="execution failed"):
        EspeakProvider("/fake/espeak").phonemize_many(("Haus",), "de-DE")


@pytest.mark.parametrize("stdout", ["one\n", "one\ntwo\nthree\n"])
def test_batch_rejects_output_cardinality_mismatch(
    monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: _completed(stdout),
    )

    with pytest.raises(ProviderOutputError, match=r"returned .* results for 2 inputs"):
        EspeakProvider("/fake/espeak").phonemize_many(("Haus", "Welt"), "de-DE")


def test_batch_uses_raw_output_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: _completed("  Haus output  \n   \n"),
    )

    result = EspeakProvider("/fake/espeak").phonemize_many(("Haus", "Welt"), "de-DE")

    assert result == ("Haus output", None)


def test_engine_uses_real_espeak_batch_method(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return _completed("one ipa\ntwo ipa\nthree ipa\n")

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)
    provider = EspeakProvider("/fake/espeak")

    with Phonemizer("de-DE", lexicons=[], fallback=provider) as engine:
        results = engine.lookup_many(("one", "two", "three"))

    assert len(calls) == 1
    assert [result.pronunciation if result else None for result in results] == [
        "one ipa",
        "two ipa",
        "three ipa",
    ]


def test_engine_sends_only_lexicon_misses_to_espeak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return _completed("missing-a ipa\nmissing-b ipa\n")

    def lookup_lexicon(
        _self: Phonemizer, token: str, *, tag: str | None = None
    ) -> PronunciationToken | None:
        return _lexical_result(token) if token in {"known", "known-two"} else None

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)
    monkeypatch.setattr(Phonemizer, "lookup_lexicon", lookup_lexicon)
    provider = EspeakProvider("/fake/espeak")

    with Phonemizer("de-DE", lexicons=[], fallback=provider) as engine:
        results = engine.lookup_many(("known", "missing-a", "known-two", "missing-b"))

    assert len(calls) == 1
    assert calls[0]["input"] == "missing-a\nmissing-b\n"
    assert [result.source if result else None for result in results] == [
        "lexicon",
        "provider",
        "lexicon",
        "provider",
    ]


def test_all_lexicon_hits_do_not_invoke_espeak(monkeypatch: pytest.MonkeyPatch) -> None:
    def lookup_lexicon(
        _self: Phonemizer, token: str, *, tag: str | None = None
    ) -> PronunciationToken:
        return _lexical_result(token)

    monkeypatch.setattr(Phonemizer, "lookup_lexicon", lookup_lexicon)
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: pytest.fail("all-hit batch must not invoke eSpeak"),
    )

    with Phonemizer("de-DE", lexicons=[], fallback=EspeakProvider("/fake/espeak")) as engine:
        results = engine.lookup_many(tuple(f"known-{index}" for index in range(10)))

    assert len(results) == 10
    assert all(result is not None and result.source == "lexicon" for result in results)


def test_ten_misses_use_one_espeak_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        calls.append(kwargs)
        return _completed("\n".join(f"ipa-{index}" for index in range(10)) + "\n")

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)

    with Phonemizer("de-DE", lexicons=[], fallback=EspeakProvider("/fake/espeak")) as engine:
        results = engine.lookup_many(tuple(f"missing-{index}" for index in range(10)))

    assert len(calls) == 1
    assert len(results) == 10


@pytest.mark.skipif(
    shutil.which("espeak-ng") is None and shutil.which("espeak") is None,
    reason="eSpeak is not installed",
)
def test_real_espeak_batch_matches_scalar() -> None:
    provider = EspeakProvider()
    examples = ("Haus", "Welt", "Datei")

    scalar = tuple(provider.phonemize(text, "de-DE") for text in examples)
    batch = provider.phonemize_many(examples, "de-DE")

    assert batch == scalar
