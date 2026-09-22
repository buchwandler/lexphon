from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import g2lex

from .errors import LexiconNotUsableError, UnsupportedAlphabetError
from .language import is_lexicon_language_compatible
from .store import DataStore

_NORMALIZABLE_ENCODINGS = frozenset({"ipa", "unicodeipa", "arpabet", "cmu", "cmudict"})


@dataclass(slots=True)
class OpenedLexiconLayer:
    identifier: str
    encoding: str
    lexicon: Any


def open_installed_pronunciation_layer(
    store: DataStore,
    language: str,
    identifier: str,
    *,
    opener: Callable[[Path], Any] | None = None,
) -> OpenedLexiconLayer:
    metadata = store.metadata(identifier)
    kind = metadata.get("kind")
    if kind != "pronunciation":
        raise LexiconNotUsableError(
            f"lexicon {identifier!r} has kind {kind!r}; only pronunciation lexica can be layers"
        )

    metadata_language = metadata.get("language")
    if not isinstance(metadata_language, str) or not is_lexicon_language_compatible(
        language, metadata_language
    ):
        raise LexiconNotUsableError(
            f"lexicon {identifier!r} language {metadata.get('language')!r} is not compatible"
            f" with profile language {language!r}"
        )

    encoding = metadata.get("phoneme_encoding")
    if not isinstance(encoding, str) or encoding.casefold() == "none":
        raise LexiconNotUsableError(
            f"lexicon {identifier!r} has no pronunciation alphabet and cannot be a layer"
        )

    open_asset = opener or g2lex.open
    return OpenedLexiconLayer(
        identifier=identifier,
        encoding=encoding,
        lexicon=open_asset(store.path(identifier)),
    )


def ensure_normalizable_encoding(encoding: str, identifier: str) -> None:
    if encoding.casefold().replace("-", "") not in _NORMALIZABLE_ENCODINGS:
        raise UnsupportedAlphabetError(
            f"unsupported pronunciation encoding {encoding!r} for {identifier!r}"
        )
