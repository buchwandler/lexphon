from types import SimpleNamespace

import pytest

from lexphon.errors import ProviderExecutionError, ProviderUnavailableError
from lexphon.providers import EspeakProvider


def test_espeak_provider_requires_an_installed_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lexphon.providers.shutil.which", lambda name: None)
    with pytest.raises(ProviderUnavailableError, match="not installed"):
        EspeakProvider()


def test_espeak_provider_returns_raw_source_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(tuple(command))
        return SimpleNamespace(returncode=0, stdout="(en)fˈIl(de)\n")

    monkeypatch.setattr("lexphon.providers.subprocess.run", run)
    result = EspeakProvider("/fake/espeak").phonemize("File", "de_DE")
    assert result == "(en)fˈIl(de)"
    assert calls == [("/fake/espeak", "-q", "--ipa=3", "-v", "de-de", "File")]


def test_espeak_provider_execution_failure_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="ignored"),
    )
    with pytest.raises(ProviderExecutionError):
        EspeakProvider("/fake/espeak").phonemize("Hallo", "de_DE")


def test_espeak_provider_empty_output_is_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lexphon.providers.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=" \n"),
    )
    assert EspeakProvider("/fake/espeak").phonemize("Hallo", "de_DE") is None
