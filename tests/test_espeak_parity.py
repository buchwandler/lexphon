"""Real provider parity tests for native/CLI/auto eSpeak modes.

These tests require a compatible eSpeak installation with both CLI and native
library available. They are skipped when the environment cannot provide both backends.
"""

from __future__ import annotations

import pytest

from lexphon.providers import EspeakProvider

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _ipa_assertions import assert_same_ipa
# Representative corpus for parity testing
_CORPUS = (
    "hello",
    "we're",
    "I'm",
    "we've",
    "we'll",
    "the",
    "and",
    "to",
)

_LANGUAGE = "en-US"


def _has_native_backend() -> bool:
    """Check if native eSpeak backend is available."""
    try:
        provider = EspeakProvider(mode="native")
        result = provider.phonemize("test", _LANGUAGE)
        provider.close()
        return result is not None
    except Exception:
        return False


def _has_cli_backend() -> bool:
    """Check if CLI eSpeak backend is available."""
    try:
        provider = EspeakProvider(mode="cli")
        result = provider.phonemize("test", _LANGUAGE)
        provider.close()
        return result is not None
    except Exception:
        return False


_needs_both_backends = pytest.mark.skipif(
    not (_has_native_backend() and _has_cli_backend()),
    reason="Requires both native and CLI eSpeak backends",
)


@_needs_both_backends
class TestProviderParity:
    """Test that all eSpeak modes produce identical output."""

    def test_native_equals_cli(self) -> None:
        """native mode produces same IPA as CLI mode for all corpus items."""
        native = EspeakProvider(mode="native")
        cli = EspeakProvider(mode="cli")
        try:
            for text in _CORPUS:
                native_result = native.phonemize(text, _LANGUAGE)
                cli_result = cli.phonemize(text, _LANGUAGE)
                assert_same_ipa(
                    text=text,
                    left_name="native",
                    left=native_result,
                    right_name="cli",
                    right=cli_result,
                    language=_LANGUAGE,
                )
        finally:
            native.close()
            cli.close()

    def test_auto_equals_cli(self) -> None:
        """auto mode produces same IPA as CLI mode for all corpus items."""
        auto = EspeakProvider(mode="auto")
        cli = EspeakProvider(mode="cli")
        try:
            for text in _CORPUS:
                auto_result = auto.phonemize(text, _LANGUAGE)
                cli_result = cli.phonemize(text, _LANGUAGE)
                assert_same_ipa(
                    text=text,
                    left_name="auto",
                    left=auto_result,
                    right_name="cli",
                    right=cli_result,
                    language=_LANGUAGE,
                )
        finally:
            auto.close()
            cli.close()


@_needs_both_backends
class TestBatchParity:
    """Test batch consistency: scalar result == batch result for each item."""

    def test_native_scalar_equals_batch(self) -> None:
        """Each scalar result equals the corresponding batch result for native mode."""
        provider = EspeakProvider(mode="native")
        try:
            batch_results = provider.phonemize_many(_CORPUS, _LANGUAGE)
            assert len(batch_results) == len(_CORPUS)
            for i, text in enumerate(_CORPUS):
                scalar_result = provider.phonemize(text, _LANGUAGE)
                assert scalar_result == batch_results[i], (
                    f"Mismatch for {text!r}: scalar={scalar_result!r} != batch={batch_results[i]!r}"
                )
        finally:
            provider.close()

    def test_cli_scalar_equals_batch(self) -> None:
        """Each scalar result equals the corresponding batch result for CLI mode."""
        provider = EspeakProvider(mode="cli")
        try:
            batch_results = provider.phonemize_many(_CORPUS, _LANGUAGE)
            assert len(batch_results) == len(_CORPUS)
            for i, text in enumerate(_CORPUS):
                scalar_result = provider.phonemize(text, _LANGUAGE)
                assert scalar_result == batch_results[i], (
                    f"Mismatch for {text!r}: scalar={scalar_result!r} != batch={batch_results[i]!r}"
                )
        finally:
            provider.close()

    def test_native_batch_equals_cli_batch(self) -> None:
        """Native batch results equal CLI batch results."""
        native = EspeakProvider(mode="native")
        cli = EspeakProvider(mode="cli")
        try:
            native_results = native.phonemize_many(_CORPUS, _LANGUAGE)
            cli_results = cli.phonemize_many(_CORPUS, _LANGUAGE)
            assert len(native_results) == len(cli_results)
            for i, text in enumerate(_CORPUS):
                assert_same_ipa(
                    text=text,
                    left_name="native_batch",
                    left=native_results[i],
                    right_name="cli_batch",
                    right=cli_results[i],
                    language=_LANGUAGE,
                )
        finally:
            native.close()
            cli.close()

    def test_batch_handles_empty_input(self) -> None:
        """Batch handles empty input tuple."""
        provider = EspeakProvider(mode="auto")
        try:
            result = provider.phonemize_many((), _LANGUAGE)
            assert result == ()
        finally:
            provider.close()

    def test_batch_handles_empty_string(self) -> None:
        """Batch handles empty string items."""
        provider = EspeakProvider(mode="auto")
        try:
            texts = ("hello", "", "world")
            results = provider.phonemize_many(texts, _LANGUAGE)
            assert len(results) == 3
            assert results[1] is None  # empty string returns None
        finally:
            provider.close()
