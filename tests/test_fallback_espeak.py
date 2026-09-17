from __future__ import annotations

from types import SimpleNamespace

import pytest

from lexphon.errors import ProviderExecutionError, ProviderOutputError, ProviderUnavailableError
from lexphon.providers import EspeakProvider


class FakeRuntime:
    def __init__(self, output: object = "raw") -> None:
        self.info = SimpleNamespace(
            executable="/fake/espeak",
            version="1.2.3",
            implementation="native",
            requested_mode="auto",
            phoneme_output_api="phonemize",
            phoneme_parity="exact",
            exact_clause_api="exact_clause",
            fallback_code=None,
            fallback_reason=None,
        )
        self.output = output
        self.scalar_calls: list[tuple[str, dict[str, object]]] = []
        self.batch_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        self.closed = False

    def phonemize(self, text: str, **kwargs: object) -> object:
        self.scalar_calls.append((text, kwargs))
        return self.output

    def phonemize_many(self, texts: tuple[str, ...], **kwargs: object) -> object:
        self.batch_calls.append((texts, kwargs))
        if isinstance(self.output, list):
            return self.output
        return [self.output] * len(texts)

    def close(self) -> None:
        self.closed = True


def test_espeak_provider_passes_tied_ipa_policy_to_scalar_and_batch() -> None:
    runtime = FakeRuntime(output="  raw  ")
    provider = EspeakProvider(runtime=runtime)

    assert provider.phonemize("Haus", "de_DE") == "raw"
    assert provider.phonemize_many(("Haus", "Welt"), "de_DE") == ("raw", "raw")

    expected = {"voice": "de-de", "use_tie": True, "tie_char": "\u200d"}
    assert runtime.scalar_calls == [("Haus", expected)]
    assert runtime.batch_calls == [(("Haus", "Welt"), expected)]


def test_espeak_provider_empty_output_is_a_miss() -> None:
    runtime = FakeRuntime(output=" ")
    provider = EspeakProvider(runtime=runtime)

    assert provider.phonemize("Hallo", "de_DE") is None
    assert provider.phonemize_many(("Hallo",), "de_DE") == (None,)


def test_espeak_provider_maps_runtime_execution_failures() -> None:
    class FailingRuntime(FakeRuntime):
        def phonemize(self, _text: str, **_kwargs: object) -> str:
            raise RuntimeError("failed")

    with pytest.raises(ProviderExecutionError, match="execution failed"):
        EspeakProvider(runtime=FailingRuntime()).phonemize("Hallo", "de_DE")


def test_espeak_provider_rejects_malformed_batch_output() -> None:
    runtime = FakeRuntime(output="not-a-sequence")
    runtime.phonemize_many = lambda *_args, **_kwargs: "malformed"  # type: ignore[method-assign]

    with pytest.raises(ProviderOutputError, match="invalid batch output"):
        EspeakProvider(runtime=runtime).phonemize_many(("Haus",), "de_DE")


def test_espeak_provider_rejects_batch_cardinality_mismatch() -> None:
    runtime = FakeRuntime(output=[])
    runtime.phonemize_many = lambda *_args, **_kwargs: ["only-one"]  # type: ignore[method-assign]

    with pytest.raises(ProviderOutputError, match="returned 1 results for 2 inputs"):
        EspeakProvider(runtime=runtime).phonemize_many(("Haus", "Welt"), "de_DE")


def test_espeak_provider_reports_runtime_diagnostics_and_closes_injected_runtime() -> None:
    runtime = FakeRuntime()
    provider = EspeakProvider(runtime=runtime)

    assert provider.runtime_info is runtime.info
    assert provider.executable == "/fake/espeak"
    assert provider.version == "1.2.3"

    provider.close()
    assert runtime.closed is False


def test_espeak_provider_closes_runtime_it_constructed(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = FakeRuntime()
    captured: dict[str, object] = {}

    class RuntimeFactory:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.info = runtime.info

        def close(self) -> None:
            runtime.close()

    monkeypatch.setattr(
        "lexphon.providers.importlib.import_module",
        lambda _name: SimpleNamespace(EspeakRuntime=RuntimeFactory),
    )
    provider = EspeakProvider()

    assert captured["mode"] == "auto"
    provider.close()
    assert runtime.closed is True


def test_explicit_executable_preserves_cli_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class RuntimeFactory:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.info = SimpleNamespace(executable="/custom/espeak", version=None)

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "lexphon.providers.importlib.import_module",
        lambda _name: SimpleNamespace(EspeakRuntime=RuntimeFactory),
    )
    provider = EspeakProvider("/custom/espeak")

    assert captured == {
        "mode": "cli",
        "executable": "/custom/espeak",
        "library": None,
        "data": None,
        "timeout": None,
    }
    provider.close()


def test_espeak_runtime_dependency_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_name: str) -> object:
        raise ImportError("missing runtime")

    monkeypatch.setattr("lexphon.providers.importlib.import_module", missing)
    with pytest.raises(ProviderUnavailableError, match="requires espeakng-runtime"):
        EspeakProvider()


def test_espeak_runtime_initialization_failure_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RuntimeFactory:
        def __init__(self, **_kwargs: object) -> None:
            raise RuntimeError("no backend")

    monkeypatch.setattr(
        "lexphon.providers.importlib.import_module",
        lambda _name: SimpleNamespace(EspeakRuntime=RuntimeFactory),
    )
    with pytest.raises(ProviderUnavailableError, match="could not be initialized"):
        EspeakProvider()
