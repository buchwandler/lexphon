"""Lexicon-driven phonemization on top of G2Lex."""

from __future__ import annotations

from ._version import __version__
from .engine import Phonemizer
from .errors import (
    CatalogError,
    DataDownloadError,
    DataIntegrityError,
    LexiconNotInstalledError,
    LexiconNotUsableError,
    LexphonError,
    UnknownWordError,
    UnsupportedAlphabetError,
)
from .fallback import EspeakFallback, FallbackPronunciation, GoruutFallback
from .models import (
    PhonemizationResult,
    PronunciationLanguageMarker,
    PronunciationToken,
    PronunciationVariant,
)
from .pronunciation import parse_pronunciation_controls, strip_language_controls
from .store import DataStore

__all__ = [
    "CatalogError",
    "DataDownloadError",
    "DataIntegrityError",
    "DataStore",
    "EspeakFallback",
    "FallbackPronunciation",
    "GoruutFallback",
    "LexiconNotInstalledError",
    "LexiconNotUsableError",
    "LexphonError",
    "PhonemizationResult",
    "Phonemizer",
    "PronunciationLanguageMarker",
    "PronunciationToken",
    "PronunciationVariant",
    "UnknownWordError",
    "UnsupportedAlphabetError",
    "__version__",
    "parse_pronunciation_controls",
    "strip_language_controls",
]
