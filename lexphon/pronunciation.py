"""Source-neutral pronunciation cleanup and provenance helpers."""

from __future__ import annotations

import re
import unicodedata

from .language import normalize_language_tag
from .models import PronunciationLanguageMarker, PronunciationVariant

_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*")


def _is_format(character: str) -> bool:
    return unicodedata.category(character) == "Cf"


def _marker_end(source: str, start: int) -> tuple[int, str] | None:
    if start >= len(source) or source[start] != "(":
        return None
    end = source.find(")", start + 1)
    if end < 0:
        return None
    candidate = "".join(
        character for character in source[start + 1 : end] if not _is_format(character)
    )
    if _LANGUAGE_TAG.fullmatch(candidate) is None:
        return None
    return end + 1, normalize_language_tag(candidate)


def _strip_language_controls(
    source: str,
) -> tuple[str, tuple[PronunciationLanguageMarker, ...]]:
    """Remove confidently recognized provider language controls in one scan.

    Unicode format characters are consumed only when directly attached to a
    recognized control. Other format characters remain part of the source.
    Offsets are calculated against the final NFC-normalized clean value.
    """
    clean_parts: list[str] = []
    marker_positions: list[tuple[str, int]] = []
    index = 0
    clean_position = 0

    while index < len(source):
        marker_start = index
        if _is_format(source[index]):
            while marker_start < len(source) and _is_format(source[marker_start]):
                marker_start += 1
            marker = _marker_end(source, marker_start)
            if marker is not None:
                marker_end, language = marker
                while marker_end < len(source) and _is_format(source[marker_end]):
                    marker_end += 1
                marker_positions.append((language, clean_position))
                index = marker_end
                continue
        marker = _marker_end(source, marker_start)
        if marker is not None:
            marker_end, language = marker
            marker_positions.append((language, clean_position))
            index = marker_end
            continue

        clean_parts.append(source[index])
        clean_position += 1
        index += 1

    clean_source = "".join(clean_parts)
    clean = unicodedata.normalize("NFC", clean_source)
    markers = tuple(
        PronunciationLanguageMarker(
            language=language,
            ipa_offset=len(unicodedata.normalize("NFC", clean_source[:position])),
        )
        for language, position in marker_positions
    )
    return clean, markers


def parse_pronunciation_controls(source: str) -> PronunciationVariant:
    """Parse provider controls and return clean IPA plus source provenance."""
    if not isinstance(source, str):
        raise TypeError("pronunciation source must be a string")
    pronunciation, markers = _strip_language_controls(source)
    return PronunciationVariant(
        pronunciation=pronunciation,
        source_pronunciation=source,
        language_markers=markers,
    )
