"""Reference provider registry and normalized reference execution."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any

from lexphon.alphabets import normalize_pronunciation
from lexphon.errors import ProviderOutputError
from lexphon.providers import BatchPronunciationProvider, EspeakProvider, PronunciationProvider

from .model import ProviderSpec, ReferenceResult
from .progress import ProgressReporter

REFERENCE_FACTORIES = {"espeak": EspeakProvider}
REFERENCE_VERSION_TIMEOUT_SECONDS = 5.0


def create_reference(name: str) -> PronunciationProvider:
    try:
        factory = REFERENCE_FACTORIES[name]
    except KeyError as error:
        raise ValueError(f"unsupported reference {name!r}") from error
    return factory()


def reference_version(provider: PronunciationProvider) -> str | None:
    executable = getattr(provider, "executable", None)
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=REFERENCE_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else None


def reference_relationship(lexicon_id: str, provider_name: str) -> str:
    if provider_name == "espeak" and lexicon_id.endswith(":espeak"):
        return "same_source_family"
    return "independent" if provider_name else "unknown"


def provider_spec(
    provider: PronunciationProvider,
    *,
    language: str,
    lexicon_id: str,
) -> ProviderSpec:
    return ProviderSpec(
        name=str(getattr(provider, "name", provider.__class__.__name__.casefold())),
        source_encoding=str(getattr(provider, "source_encoding", "ipa")),
        version=reference_version(provider),
        language=language,
        relationship=reference_relationship(lexicon_id, str(getattr(provider, "name", "unknown"))),
    )


def _reference_result(
    raw: object,
    provider: PronunciationProvider,
    *,
    version: str | None,
) -> ReferenceResult:
    name = str(getattr(provider, "name", "unknown"))
    encoding = str(getattr(provider, "source_encoding", "ipa"))
    if raw is None:
        return ReferenceResult(
            "unavailable", provider=name, source_encoding=encoding, version=version
        )
    if not isinstance(raw, str) or not raw.strip():
        return ReferenceResult(
            "error",
            error="reference returned malformed pronunciation",
            provider=name,
            source_encoding=encoding,
            version=version,
        )
    try:
        normalized = normalize_pronunciation(raw, encoding).pronunciation
    except Exception as error:  # noqa: BLE001
        return ReferenceResult(
            "error", error=str(error), provider=name, source_encoding=encoding, version=version
        )
    return ReferenceResult(
        "ok",
        normalized,
        raw.strip(),
        provider=name,
        source_encoding=encoding,
        version=version,
    )


def _call_reference(
    provider: PronunciationProvider,
    word: str,
    language: str,
    *,
    version: str | None,
) -> ReferenceResult:
    try:
        raw = provider.phonemize(word, language)
    except Exception as error:  # noqa: BLE001
        return ReferenceResult(
            "error", error=str(error), provider=getattr(provider, "name", None), version=version
        )
    return _reference_result(raw, provider, version=version)


def _error_text(error: Exception) -> str:
    return str(error) or error.__class__.__name__


def _stage(progress: ProgressReporter | None, label: str, message: str) -> None:
    if progress is not None:
        progress.stage(label, "reference", message)


def generate_references(
    words: Sequence[str],
    *,
    language: str,
    provider: PronunciationProvider,
    provider_info: ProviderSpec | None = None,
    progress: ProgressReporter | None = None,
    progress_lexicon_id: str | None = None,
) -> dict[str, ReferenceResult]:
    values = tuple(words)
    if not values:
        return {}
    version = provider_info.version if provider_info is not None else reference_version(provider)
    label = progress_lexicon_id or str(getattr(provider, "name", "reference"))
    if isinstance(provider, BatchPronunciationProvider):
        _stage(
            progress,
            label,
            f"generating {len(values)} pronunciations with batch provider {getattr(provider, 'name', 'unknown')}",
        )
        try:
            raw_values = tuple(provider.phonemize_many(values, language))
            if len(raw_values) != len(values):
                raise ProviderOutputError(
                    f"reference returned {len(raw_values)} results for {len(values)} words"
                )
            results = {
                word: _reference_result(raw, provider, version=version)
                for word, raw in zip(values, raw_values, strict=True)
            }
            _stage(progress, label, "batch complete")
            return results
        except Exception as error:  # noqa: BLE001
            _stage(progress, label, f"batch provider failed: {_error_text(error)}")
            _stage(progress, label, f"falling back to individual calls for {len(values)} words")
            results = {}
            for current, word in enumerate(values, 1):
                results[word] = _call_reference(provider, word, language, version=version)
                if progress is not None:
                    progress.counter(label, "reference fallback", current, len(values))
            return results
    _stage(
        progress,
        label,
        f"generating {len(values)} pronunciations with individual provider {getattr(provider, 'name', 'unknown')}",
    )
    results = {}
    for current, word in enumerate(values, 1):
        results[word] = _call_reference(provider, word, language, version=version)
        if progress is not None:
            progress.counter(label, "reference", current, len(values))
    return results


def reference_to_dict(result: ReferenceResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "ipa": result.ipa,
        "source_pronunciation": result.source_pronunciation,
        "error": result.error,
        "name": result.provider,
        "source_encoding": result.source_encoding,
        "version": result.version,
    }
