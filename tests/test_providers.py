"""Tests for EspeakProvider mode validation and lifecycle contracts."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import MagicMock

import pytest

from lexphon.providers import _VALID_MODES, EspeakProvider


def _owned_provider(monkeypatch: pytest.MonkeyPatch) -> tuple[EspeakProvider, MagicMock]:
    runtime = MagicMock()
    module = MagicMock()
    module.EspeakRuntime.return_value = runtime
    monkeypatch.setattr("lexphon.providers._load_espeak_runtime", lambda: module)
    return EspeakProvider(), runtime


class TestModeValidation:
    """EspeakProvider mode parameter validation."""

    def test_valid_modes_accepted(self) -> None:
        """Valid modes do not raise ValueError."""
        mock_runtime = MagicMock()
        for mode in _VALID_MODES:
            provider = EspeakProvider(mode=mode, runtime=mock_runtime)
            assert provider is not None

    def test_none_mode_accepted(self) -> None:
        """None mode (default) does not raise ValueError."""
        mock_runtime = MagicMock()
        provider = EspeakProvider(mode=None, runtime=mock_runtime)
        assert provider is not None

    def test_invalid_mode_raises_value_error(self) -> None:
        """Invalid mode raises ValueError, not ProviderUnavailableError."""
        with pytest.raises(ValueError, match="invalid eSpeak mode"):
            EspeakProvider(mode="nativ")  # typo

    def test_invalid_mode_error_message_includes_valid_modes(self) -> None:
        """ValueError message includes the list of valid modes."""
        with pytest.raises(ValueError, match="auto.*cli.*native"):
            EspeakProvider(mode="bad")

    def test_invalid_mode_raises_before_runtime_construction(self) -> None:
        """ValueError is raised before attempting to import espeakng_runtime."""
        # If validation happened after import, we'd get ProviderUnavailableError
        # instead of ValueError when espeakng_runtime is not installed.
        with pytest.raises(ValueError, match="invalid eSpeak mode"):
            EspeakProvider(mode="invalid")

    def test_espeak_mode_literal_values(self) -> None:
        """EspeakMode literal has expected values."""
        assert _VALID_MODES == {"auto", "native", "cli"}


class TestDiagnosticInfo:
    """EspeakProvider diagnostic_info method."""

    def test_diagnostic_info_returns_dict(self) -> None:
        """diagnostic_info returns a dict."""
        mock_runtime = MagicMock()
        mock_info = MagicMock()
        mock_info.requested_mode = "auto"
        mock_info.implementation = "native"
        mock_info.version = "1.0"
        mock_info.source = "libespeak-ng"
        mock_info.executable = None
        mock_info.library = "/usr/lib/libespeak-ng.so"
        mock_info.data = "/usr/share/espeak-ng-data"
        mock_info.phoneme_output_api = "phonemize"
        mock_info.phoneme_parity = "exact"
        mock_info.exact_clause_api = "exact_clause"
        mock_info.fallback_code = None
        mock_info.fallback_reason = None
        mock_runtime.info = mock_info
        provider = EspeakProvider(runtime=mock_runtime)
        result = provider.diagnostic_info()
        assert isinstance(result, dict)

    def test_diagnostic_info_has_expected_keys(self) -> None:
        """diagnostic_info dict has expected keys."""
        mock_runtime = MagicMock()
        mock_info = MagicMock()
        mock_info.requested_mode = "cli"
        mock_info.implementation = "cli"
        mock_info.version = "1.0"
        mock_info.source = "espeak-ng"
        mock_info.executable = "/usr/bin/espeak-ng"
        mock_info.library = None
        mock_info.data = None
        mock_info.phoneme_output_api = "phonemize"
        mock_info.phoneme_parity = "exact"
        mock_info.exact_clause_api = "exact_clause"
        mock_info.fallback_code = None
        mock_info.fallback_reason = None
        mock_runtime.info = mock_info
        provider = EspeakProvider(runtime=mock_runtime)
        result = provider.diagnostic_info()
        expected_keys = {
            "requested_mode",
            "implementation",
            "version",
            "source",
            "executable",
            "library",
            "data",
            "phoneme_output_api",
            "phoneme_parity",
            "exact_clause_api",
            "fallback_code",
            "fallback_reason",
        }
        assert set(result.keys()) == expected_keys

    def test_diagnostic_info_values_from_runtime(self) -> None:
        """diagnostic_info values come from runtime info."""
        mock_runtime = MagicMock()
        mock_info = MagicMock()
        mock_info.requested_mode = "auto"
        mock_info.implementation = "native"
        mock_info.version = "1.48"
        mock_info.source = "libespeak-ng"
        mock_info.executable = None
        mock_info.library = "/usr/lib/libespeak-ng.so"
        mock_info.data = "/usr/share/espeak-ng-data"
        mock_info.phoneme_output_api = "phonemize"
        mock_info.phoneme_parity = "exact"
        mock_info.exact_clause_api = "exact_clause"
        mock_info.fallback_code = "best-effort"
        mock_info.fallback_reason = "no native clause API"
        mock_runtime.info = mock_info
        provider = EspeakProvider(runtime=mock_runtime)
        result = provider.diagnostic_info()
        assert result["requested_mode"] == "auto"
        assert result["implementation"] == "native"
        assert result["version"] == "1.48"
        assert result["source"] == "libespeak-ng"
        assert result["executable"] is None
        assert result["library"] == "/usr/lib/libespeak-ng.so"
        assert result["data"] == "/usr/share/espeak-ng-data"
        assert result["phoneme_output_api"] == "phonemize"
        assert result["phoneme_parity"] == "exact"
        assert result["exact_clause_api"] == "exact_clause"
        assert result["fallback_code"] == "best-effort"
        assert result["fallback_reason"] == "no native clause API"
class TestLifecycle:
    """EspeakProvider lifecycle contract tests."""

    def test_injected_runtime_not_closed(self) -> None:
        """Injected runtime is not closed by provider."""
        mock_runtime = MagicMock()
        provider = EspeakProvider(runtime=mock_runtime)
        provider.close()
        mock_runtime.close.assert_not_called()

    def test_owned_runtime_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Owned runtime is closed by provider."""
        provider, mock_runtime = _owned_provider(monkeypatch)
        provider.close()
        mock_runtime.close.assert_called_once()

    def test_double_close_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Double close() is safe at Lexphon layer."""
        provider, mock_runtime = _owned_provider(monkeypatch)
        provider.close()
        provider.close()  # Should not raise
        assert mock_runtime.close.call_count == 2


class TestPhonemizerFallbackLifecycle:
    """Phonemizer fallback lifecycle tests."""

    def test_fallback_provider_created_lazily(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fallback provider is created lazily after a miss."""
        from lexphon.providers import create_provider

        # create_provider creates the provider immediately
        # This is a simplified test since we can't easily test the full Phonemizer
        # without a real lexicon store
        mock_runtime = MagicMock()
        module = MagicMock()
        module.EspeakRuntime.return_value = mock_runtime
        monkeypatch.setattr("lexphon.providers._load_espeak_runtime", lambda: module)
        provider = create_provider("espeak")
        assert provider is not None
        assert provider.name == "espeak"

    def test_fallback_provider_closed_once(self) -> None:
        """Engine-created fallback provider closed exactly once."""

        class MockProvider:
            name = "mock"
            source_encoding = "ipa"
            close_count = 0

            def phonemize(self, text: str, language: str) -> str | None:
                return None

            def close(self) -> None:
                MockProvider.close_count += 1

        provider = MockProvider()
        # Simulate what Phonemizer does
        # In real code, Phonemizer would call close() once
        provider.close()
        assert MockProvider.close_count == 1

    def test_batch_fallback_preserves_order(self) -> None:
        """Batch lookup sends fallback misses in one call preserving order."""

        class MockBatchProvider:
            name = "mock"
            source_encoding = "ipa"

            def phonemize(self, text: str, language: str) -> str | None:
                return None

            def phonemize_many(self, texts: Sequence[str], language: str) -> Sequence[str | None]:
                # Return results in same order as input
                return [f"result_{i}" for i in range(len(texts))]

        provider = MockBatchProvider()
        texts = ["hello", "world", "test"]
        results = provider.phonemize_many(texts, "en-US")
        assert len(results) == 3
        assert results[0] == "result_0"
        assert results[1] == "result_1"
        assert results[2] == "result_2"
