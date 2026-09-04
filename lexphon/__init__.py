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
from .models import PhonemizationResult, PronunciationToken
from .store import DataStore

__all__ = [
    "CatalogError",
    "DataDownloadError",
    "DataIntegrityError",
    "DataStore",
    "LexiconNotInstalledError",
    "LexiconNotUsableError",
    "LexphonError",
    "PhonemizationResult",
    "Phonemizer",
    "PronunciationToken",
    "UnknownWordError",
    "UnsupportedAlphabetError",
    "__version__",
]
