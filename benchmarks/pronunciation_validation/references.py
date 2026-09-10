"""Reference provider registry and normalized reference execution."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any

from lexphon.alphabets import normalize_pronunciation
from lexphon.errors import ProviderOutputError
from lexphon.providers import BatchPronunciationProvider, EspeakProvider, PronunciationProvider

from .model import ProviderSpec, ReferenceResult

REFERENCE_FACTORIES = {"espeak": EspeakProvider}


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
            [str(executable), "--version"], check=False, capture_output=True, text=True, encoding="utf-8"
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


def _reference_result(raw: object, provider: PronunciationProvider) -> ReferenceResult:
    name = str(getattr(provider, "name", "unknown"))
    encoding = str(getattr(provider, "source_encoding", "ipa"))
    version = reference_version(provider)
    if raw is None:
        return ReferenceResult("unavailable", provider=name, source_encoding=encoding, version=version)
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


def _call_reference(provider: PronunciationProvider, word: str, language: str) -> ReferenceResult:
    try:
        raw = provider.phonemize(word, language)
    except Exception as error:  # noqa: BLE001
        return ReferenceResult("error", error=str(error), provider=getattr(provider, "name", None))
    return _reference_result(raw, provider)


def generate_references(
    words: Sequence[str],
    *,
    language: str,
    provider: PronunciationProvider,
) -> dict[str, ReferenceResult]:
    values = tuple(words)
    if not values:
        return {}
    if isinstance(provider, BatchPronunciationProvider):
        try:
            raw_values = tuple(provider.phonemize_many(values, language))
            if len(raw_values) != len(values):
                raise ProviderOutputError(
                    f"reference returned {len(raw_values)} results for {len(values)} words"
                )
            return {word: _reference_result(raw, provider) for word, raw in zip(values, raw_values)}
        except Exception:  # noqa: BLE001
            return {word: _call_reference(provider, word, language) for word in values}
    return {word: _call_reference(provider, word, language) for word in values}


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
