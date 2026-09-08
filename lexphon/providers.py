from __future__ import annotations

import importlib
import shutil
import subprocess
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from .errors import ProviderExecutionError, ProviderOutputError, ProviderUnavailableError
from .language import normalize_language_tag


class PronunciationProvider(Protocol):
    name: str
    source_encoding: str

    def phonemize(self, text: str, language: str) -> str | None:
        """Return raw provider pronunciation or None for a genuine miss."""


@runtime_checkable
class BatchPronunciationProvider(PronunciationProvider, Protocol):
    def phonemize_many(self, texts: Sequence[str], language: str) -> Sequence[str | None]:
        """Return one raw result for each input text."""


def _raw_output(value: object, provider: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderOutputError(
            f"provider {provider!r} returned {type(value).__name__}, expected str or None"
        )
    value = value.strip()
    return value or None


class EspeakProvider:
    """Optional eSpeak/eSpeak-NG raw IPA provider."""

    name = "espeak"
    source_encoding = "ipa"

    def __init__(self, executable: str | None = None):
        executable_path = executable or shutil.which("espeak-ng") or shutil.which("espeak")
        if not executable_path:
            raise ProviderUnavailableError(
                "eSpeak provider requested but espeak-ng/espeak is not installed"
            )
        self.executable = executable_path

    def phonemize(self, text: str, language: str) -> str | None:
        try:
            completed = subprocess.run(
                [self.executable, "-q", "--ipa=3", "-v", normalize_language_tag(language), text],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProviderExecutionError(f"eSpeak provider execution failed: {error}") from error
        if completed.returncode != 0:
            raise ProviderExecutionError(
                f"eSpeak provider exited with status {completed.returncode}"
            )
        return _raw_output(completed.stdout, self.name)


class GoruutProvider:
    """Optional Goruut raw IPA provider through the pygoruut package."""

    name = "goruut"
    source_encoding = "ipa"

    def __init__(self, client: Any | None = None):
        if client is not None:
            self.client = client
            return
        try:
            module = importlib.import_module("pygoruut.pygoruut")
            factory = module.Pygoruut
        except (ImportError, AttributeError) as error:
            raise ProviderUnavailableError(
                "Goruut provider requested but pygoruut is not installed"
            ) from error
        try:
            self.client = factory()
        except Exception as error:
            raise ProviderUnavailableError("Goruut provider could not be initialized") from error

    def phonemize(self, text: str, language: str) -> str | None:
        try:
            value = self.client.phonemize(language=language, sentence=text)
        except Exception as error:
            raise ProviderExecutionError(f"Goruut provider execution failed: {error}") from error
        return _raw_output(value, self.name)


def create_provider(name: str) -> PronunciationProvider:
    if name == "espeak":
        return EspeakProvider()
    if name == "goruut":
        return GoruutProvider()
    raise ValueError(f"unknown provider: {name}")
