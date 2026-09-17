from __future__ import annotations

import importlib
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


def _load_espeak_runtime() -> Any:
    try:
        return importlib.import_module("espeakng_runtime")
    except ImportError as error:
        raise ProviderUnavailableError(
            "eSpeak provider requires espeakng-runtime; install lexphon with the 'espeak' extra"
        ) from error


_ESPEAK_TIE_CHAR = "\u200d"


def _espeak_phonemize_kwargs(language: str) -> dict[str, object]:
    return {
        "voice": normalize_language_tag(language),
        "use_tie": True,
        "tie_char": _ESPEAK_TIE_CHAR,
    }


class EspeakProvider:
    """Optional eSpeak/eSpeak-NG raw IPA provider through espeakng-runtime."""

    name = "espeak"
    source_encoding = "ipa"

    def __init__(
        self,
        executable: str | None = None,
        *,
        mode: str | None = None,
        library: str | None = None,
        data: str | None = None,
        timeout: float | None = None,
        runtime: object | None = None,
    ) -> None:
        self._runtime: Any
        self._owns_runtime = runtime is None
        if runtime is not None:
            self._runtime = runtime
            return

        effective_mode = mode or ("cli" if executable is not None else "auto")
        module = _load_espeak_runtime()
        try:
            self._runtime = module.EspeakRuntime(
                mode=effective_mode,
                executable=executable,
                library=library,
                data=data,
                timeout=timeout,
            )
        except Exception as error:
            raise ProviderUnavailableError(
                f"eSpeak provider could not be initialized: {error}"
            ) from error

    @property
    def runtime_info(self) -> object:
        return self._runtime.info

    @property
    def executable(self) -> str | None:
        value = getattr(self.runtime_info, "executable", None)
        return str(value) if value is not None else None

    @property
    def version(self) -> str | None:
        value = getattr(self.runtime_info, "version", None)
        return str(value) if value is not None else None

    def phonemize(self, text: str, language: str) -> str | None:
        try:
            value = self._runtime.phonemize(text, **_espeak_phonemize_kwargs(language))
        except Exception as error:
            raise ProviderExecutionError(f"eSpeak provider execution failed: {error}") from error
        return _raw_output(value, self.name)

    def phonemize_many(
        self,
        texts: Sequence[str],
        language: str,
    ) -> tuple[str | None, ...]:
        values = tuple(texts)
        if not values:
            return ()

        try:
            outputs = self._runtime.phonemize_many(values, **_espeak_phonemize_kwargs(language))
        except Exception as error:
            raise ProviderExecutionError(
                f"eSpeak provider batch execution failed: {error}"
            ) from error

        if isinstance(outputs, (str, bytes)) or not isinstance(outputs, Sequence):
            raise ProviderOutputError(
                "eSpeak provider returned an invalid batch output; expected a sequence"
            )
        if len(outputs) != len(values):
            raise ProviderOutputError(
                f"eSpeak batch returned {len(outputs)} results for {len(values)} inputs"
            )
        return tuple(_raw_output(value, self.name) for value in outputs)

    def close(self) -> None:
        if self._owns_runtime:
            self._runtime.close()


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
