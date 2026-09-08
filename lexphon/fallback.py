from __future__ import annotations

import importlib
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import LexphonError
from .models import PronunciationLanguageMarker
from .pronunciation import parse_pronunciation_controls


@dataclass(frozen=True, slots=True, eq=False)
class FallbackPronunciation:
    pronunciation: str
    provider: str
    source_pronunciation: str | None = None
    language_markers: tuple[PronunciationLanguageMarker, ...] = ()
    source_encoding: str = "ipa"
    provider_language: str | None = None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.pronunciation == other
        if not isinstance(other, FallbackPronunciation):
            return NotImplemented
        return (
            self.pronunciation,
            self.provider,
            self.source_pronunciation,
            self.language_markers,
            self.source_encoding,
            self.provider_language,
        ) == (
            other.pronunciation,
            other.provider,
            other.source_pronunciation,
            other.language_markers,
            other.source_encoding,
            other.provider_language,
        )

    def __str__(self) -> str:
        return self.pronunciation


class Fallback(Protocol):
    name: str

    def phonemize(self, text: str, language: str) -> FallbackPronunciation | str | None: ...

    def phonemize_many(
        self, texts: Sequence[str], language: str
    ) -> Sequence[FallbackPronunciation | str | None]: ...


def _normalized_output(value: object) -> str:
    return " ".join(str(value).split())


def _result(
    value: object,
    *,
    provider: str,
    language: str,
    raw_source: str | None = None,
) -> FallbackPronunciation | None:
    if isinstance(value, FallbackPronunciation):
        return value
    output = _normalized_output(value)
    if not output:
        return None
    parsed = parse_pronunciation_controls(output)
    return FallbackPronunciation(
        pronunciation=parsed.pronunciation,
        provider=provider,
        source_pronunciation=raw_source if raw_source is not None else parsed.source_pronunciation,
        language_markers=parsed.language_markers,
        provider_language=language,
    )


class EspeakFallback:
    """Optional eSpeak/eSpeak-NG IPA fallback."""

    name = "espeak"

    def __init__(self, executable: str | None = None):
        executable_path = executable or shutil.which("espeak-ng") or shutil.which("espeak")
        if not executable_path:
            raise LexphonError("eSpeak fallback requested but espeak-ng/espeak is not installed")
        self.executable = executable_path

    def phonemize(self, text: str, language: str) -> FallbackPronunciation | None:
        voice = language.lower().replace("_", "-")
        try:
            completed = subprocess.run(
                [self.executable, "-q", "--ipa=3", "-v", voice, text],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        raw_output = completed.stdout
        return _result(
            raw_output,
            provider=self.name,
            language=language,
            raw_source=raw_output,
        )

    def phonemize_many(
        self, texts: Sequence[str], language: str
    ) -> tuple[FallbackPronunciation | None, ...]:
        return tuple(self.phonemize(text, language) for text in texts)


class GoruutFallback:
    """Optional Goruut IPA fallback through the pygoruut package."""

    name = "goruut"

    def __init__(self, client: Any | None = None):
        if client is not None:
            self.client = client
            return
        try:
            module = importlib.import_module("pygoruut.pygoruut")
            factory = module.Pygoruut
        except (ImportError, AttributeError) as error:
            raise LexphonError("Goruut fallback requested but pygoruut is not installed") from error
        self.client = factory()

    def phonemize(self, text: str, language: str) -> FallbackPronunciation | None:
        try:
            value = self.client.phonemize(language=language, sentence=text)
        except Exception:  # noqa: BLE001
            return None
        return _result(value, provider=self.name, language=language)

    def phonemize_many(
        self, texts: Sequence[str], language: str
    ) -> tuple[FallbackPronunciation | None, ...]:
        return tuple(self.phonemize(text, language) for text in texts)


def create_fallback(name: str) -> Fallback:
    if name == "espeak":
        return EspeakFallback()
    if name == "goruut":
        return GoruutFallback()
    raise ValueError(f"unknown fallback: {name}")
