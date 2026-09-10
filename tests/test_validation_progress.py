from __future__ import annotations

import io
import subprocess
from types import SimpleNamespace

import pytest

from benchmarks.pronunciation_validation import run_all, runner
from benchmarks.pronunciation_validation.model import BenchmarkRunResult, BenchmarkSpec, RankedWord
from benchmarks.pronunciation_validation.progress import ProgressReporter
from benchmarks.pronunciation_validation.references import (
    REFERENCE_VERSION_TIMEOUT_SECONDS,
    generate_references,
    reference_version,
)
from benchmarks.pronunciation_validation.validation import collect_validation_rows


class BatchProvider:
    name = "fake-espeak"
    source_encoding = "ipa"
    executable = "fake-espeak"

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.batch_calls = 0
        self.individual_calls = 0

    def phonemize_many(self, words: tuple[str, ...], _language: str) -> tuple[str, ...]:
        self.batch_calls += 1
        return tuple(self.values[word] for word in words)

    def phonemize(self, _word: str, _language: str) -> str:
        self.individual_calls += 1
        raise AssertionError("successful batch must not fall back")


class FallbackProvider:
    name = "fake"
    source_encoding = "ipa"

    def phonemize_many(self, _words: tuple[str, ...], _language: str) -> tuple[str, ...]:
        raise RuntimeError("batch unavailable")

    def phonemize(self, word: str, _language: str) -> str:
        return "a" if word == "Haus" else "b"


class FakeEngine:
    def lookup_lexicon(self, word: str) -> object:
        return SimpleNamespace(
            matched_key=word,
            variants=(SimpleNamespace(pronunciation="a", source_pronunciation="a"),),
        )


def test_batch_reference_resolves_version_once(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = BatchProvider({"one": "a", "two": "b", "three": "c"})
    calls: list[tuple[object, dict[str, object]]] = []

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="fake-espeak 1.0\n", stderr="")

    monkeypatch.setattr("benchmarks.pronunciation_validation.references.subprocess.run", fake_run)
    results = generate_references(("one", "two", "three"), language="de-DE", provider=provider)

    assert len(calls) == 1
    assert provider.batch_calls == 1
    assert provider.individual_calls == 0
    assert len(results) == 3
    assert {result.version for result in results.values()} == {"fake-espeak 1.0"}


def test_reference_version_timeout_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def timeout(*_args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        raise subprocess.TimeoutExpired("fake-espeak", 1)

    monkeypatch.setattr("benchmarks.pronunciation_validation.references.subprocess.run", timeout)
    provider = SimpleNamespace(executable="fake-espeak", name="fake", source_encoding="ipa")

    assert reference_version(provider) is None
    assert seen["timeout"] == REFERENCE_VERSION_TIMEOUT_SECONDS


def test_batch_fallback_is_reported_and_keeps_results() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(stream=stream)
    results = generate_references(
        ("Haus", "Foo"),
        language="de-DE",
        provider=FallbackProvider(),
        progress=reporter,
        progress_lexicon_id="de-de:crane",
    )

    output = stream.getvalue()
    assert "batch provider failed: batch unavailable" in output
    assert "falling back to individual calls" in output
    assert "reference fallback: 2/2" in output
    assert {result.status for result in results.values()} == {"ok"}


def test_lookup_progress_is_bounded_and_finishes() -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(stream=stream)
    rows = collect_validation_rows(
        [RankedWord(index, f"word-{index}") for index in range(1, 21)],
        language="de-DE",
        engine=FakeEngine(),
        provider=FallbackProvider(),
        progress=reporter,
        progress_lexicon_id="de-de:crane",
    )

    lookup_events = [line for line in stream.getvalue().splitlines() if "] lookup:" in line]
    assert len(rows) == 20
    assert lookup_events[-1].endswith("20/20; 20 found; 0 lookup errors")
    assert len(lookup_events) < 20


def test_matrix_progress_identifies_position(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    reporter = ProgressReporter(stream=stream)
    specs = (BenchmarkSpec("de-de:one"), BenchmarkSpec("de-de:two"))

    def fake_run_spec(
        spec: BenchmarkSpec, _argv: object, *, progress: ProgressReporter
    ) -> BenchmarkRunResult:
        progress.stage(spec.lexicon_id, "completed", "ok")
        return BenchmarkRunResult(
            "completed",
            {"coverage": {"coverage_percentage": 100}, "comparison": {"compared": 1}},
        )

    monkeypatch.setattr(run_all, "run_spec", fake_run_spec)
    run_all.run_matrix(specs, progress=reporter)

    output = stream.getvalue()
    assert "[1/2] de-de:one" in output
    assert "[2/2] de-de:two" in output


def test_run_all_quiet_suppresses_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys
) -> None:
    monkeypatch.setattr(run_all, "discover_specs", lambda: (BenchmarkSpec("de-de:one"),))

    def fake_matrix(
        *_args: object, progress: ProgressReporter, **_kwargs: object
    ) -> dict[str, object]:
        assert progress.enabled is False
        return {"schema_version": 1, "benchmarks": [{"status": "completed"}]}

    monkeypatch.setattr(run_all, "run_matrix", fake_matrix)
    assert run_all.main(["--language", "de-DE", "--quiet", "--output-dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert "wrote" in captured.out


def test_cli_keyboard_interrupt_returns_130_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(run_all, "discover_specs", lambda: (BenchmarkSpec("de-de:one"),))

    def interrupted(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_all, "run_matrix", interrupted)
    assert run_all.main(["--language", "de-DE"]) == 130
    captured = capsys.readouterr()
    assert "pronunciation validation interrupted by user" in captured.err
    assert "Traceback" not in captured.err


def test_individual_cli_keyboard_interrupt_uses_stderr(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(
        runner, "run_spec", lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt)
    )

    assert runner.main_for(BenchmarkSpec("de-de:one")) == 130
    captured = capsys.readouterr()
    assert "[de-de:one] interrupted" in captured.err
    assert captured.out == ""
