from __future__ import annotations

import importlib
import shutil
import subprocess
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from .errors import (
    ProviderError,
    ProviderExecutionError,
    ProviderOutputError,
    ProviderUnavailableError,
)
from .language import normalize_language_tag

_GORUUT_LANGUAGE_ALIASES = {
    "en-us": "EnglishAmerican",
    "en-gb": "EnglishBritish",
    "de-de": "de",
    "fr-fr": "fr",
    "sv-se": "sv",
}
_GORUUT_ISO_CODES = frozenset(
    {
        "af",
        "am",
        "ar",
        "az",
        "be",
        "bn",
        "my",
        "ceb",
        "ce",
        "zh",
        "cs",
        "da",
        "nl",
        "dz",
        "de",
        "en",
        "eo",
        "fa",
        "fi",
        "fr",
        "gu",
        "ha",
        "he",
        "hi",
        "hu",
        "is",
        "id",
        "tts",
        "it",
        "jam",
        "ja",
        "jv",
        "kk",
        "ko",
        "lb",
        "mk",
        "ml",
        "ms",
        "mt",
        "mr",
        "mn",
        "ne",
        "no",
        "ps",
        "pl",
        "pt",
        "pa",
        "ro",
        "ru",
        "sk",
        "es",
        "sw",
        "sv",
        "ta",
        "te",
        "th",
        "bo",
        "tr",
        "uk",
        "ur",
        "ug",
        "vi",
        "zu",
        "hy",
        "eu",
        "bg",
        "ca",
        "ny",
        "hr",
        "et",
        "gl",
        "ka",
        "km",
        "lo",
        "lv",
        "lt",
        "sr",
        "tl",
        "yo",
        "sq",
        "an",
        "as",
        "ba",
        "bpy",
        "bs",
        "chr",
        "cu",
        "gla",
        "gle",
        "kl",
        "gn",
        "ht",
        "haw",
        "io",
        "ia",
        "kn",
        "quc",
        "kok",
        "ku",
        "ky",
        "qdb",
        "ltg",
        "la",
        "lat",
        "lfn",
        "jbo",
        "smj",
        "mi",
        "nah",
        "nci",
        "ncz",
        "nog",
        "om",
        "pap",
        "qu",
        "qya",
        "tn",
        "shn",
        "sjn",
        "sd",
        "si",
        "sl",
        "tt",
        "tk",
        "uz",
        "cyw",
        "cys",
        "yue",
    }
)


def _to_goruut_language(language: str) -> str:
    normalized = normalize_language_tag(language)
    if normalized in _GORUUT_LANGUAGE_ALIASES:
        return _GORUUT_LANGUAGE_ALIASES[normalized]
    if normalized in _GORUUT_ISO_CODES:
        return normalized
    primary = normalized.split("-", 1)[0]
    if primary in _GORUUT_ISO_CODES:
        return primary
    raise ProviderExecutionError(f"Goruut provider does not support language {language!r}")


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


    def phonemize_many(
        self,
        texts: Sequence[str],
        language: str,
    ) -> tuple[str | None, ...]:
        values = tuple(texts)
        if not values:
            return ()

        nonempty_indexes: list[int] = []
        nonempty_values: list[str] = []
        for index, value in enumerate(values):
            if "\n" in value or "\r" in value:
                raise ProviderExecutionError(
                    "eSpeak batch inputs must not contain line breaks"
                )
            if not value or not value.strip():
                continue
            nonempty_indexes.append(index)
            nonempty_values.append(value)

        if not nonempty_values:
            return tuple(None for _ in values)

        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "-q",
                    "--ipa=3",
                    "-v",
                    normalize_language_tag(language),
                ],
                input="\n".join(nonempty_values) + "\n",
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProviderExecutionError(
                f"eSpeak provider execution failed: {error}"
            ) from error
        if completed.returncode != 0:
            raise ProviderExecutionError(
                f"eSpeak provider exited with status {completed.returncode}"
            )

        lines = completed.stdout.splitlines()
        if len(lines) != len(nonempty_values):
            raise ProviderOutputError(
                "eSpeak batch returned "
                f"{len(lines)} results for {len(nonempty_values)} inputs"
            )

        result: list[str | None] = [None] * len(values)
        for index, output in zip(nonempty_indexes, lines, strict=True):
            result[index] = _raw_output(output, self.name)
        return tuple(result)

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
        goruut_language = _to_goruut_language(language)
        try:
            value = self.client.phonemize(language=goruut_language, sentence=text)
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderExecutionError(f"Goruut provider execution failed: {error}") from error
        if value is None:
            return None
        try:
            rendered = str(value)
        except Exception as error:
            raise ProviderExecutionError(
                f"Goruut provider returned an unrenderable response: {error}"
            ) from error
        return _raw_output(rendered, self.name)


def create_provider(name: str) -> PronunciationProvider:
    if name == "espeak":
        return EspeakProvider()
    if name == "goruut":
        return GoruutProvider()
    raise ValueError(f"unknown provider: {name}")
