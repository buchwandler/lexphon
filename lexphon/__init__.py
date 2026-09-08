"""Lexicon-driven phonemization on top of G2Lex."""

from __future__ import annotations

from ._version import __version__
from .alphabets import normalize_pronunciation
from .engine import Phonemizer
from .errors import (
    CatalogError,
    DataDownloadError,
    DataIntegrityError,
    LexiconNotInstalledError,
    LexiconNotUsableError,
    LexphonError,
    ProviderError,
    ProviderExecutionError,
    ProviderOutputError,
    ProviderUnavailableError,
    UnknownWordError,
    UnsupportedAlphabetError,
)
from .language import normalize_language_tag
from .models import (
    PhonemizationResult,
    PronunciationLanguageMarker,
    PronunciationSource,
    PronunciationToken,
    PronunciationVariant,
)
from .providers import (
    BatchPronunciationProvider,
    EspeakProvider,
    GoruutProvider,
    PronunciationProvider,
    create_provider,
)
from .store import DataStore

__all__ = [
    "BatchPronunciationProvider",
    "CatalogError",
    "DataDownloadError",
    "DataIntegrityError",
    "DataStore",
    "EspeakProvider",
    "GoruutProvider",
    "LexiconNotInstalledError",
    "LexiconNotUsableError",
    "LexphonError",
    "PhonemizationResult",
    "Phonemizer",
    "PronunciationLanguageMarker",
    "PronunciationProvider",
    "PronunciationSource",
    "PronunciationToken",
    "PronunciationVariant",
    "ProviderError",
    "ProviderExecutionError",
    "ProviderOutputError",
    "ProviderUnavailableError",
    "UnknownWordError",
    "UnsupportedAlphabetError",
    "__version__",
    "create_provider",
    "normalize_language_tag",
    "normalize_pronunciation",
]
