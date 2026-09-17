"""Test utility for IPA comparison with Phonodist-enhanced failure messages."""

from __future__ import annotations

import importlib
from typing import Any


def _import_phonodist() -> Any | None:
    try:
        return importlib.import_module("phonodist")
    except (ImportError, ModuleNotFoundError):
        return None


def assert_same_ipa(
    *,
    text: str,
    left_name: str,
    left: str | None,
    right_name: str,
    right: str | None,
    language: str = "en-US",
) -> None:
    """Assert two IPA strings are equal, with Phonodist classification on failure.

    If both outputs are strings and unequal, uses Phonodist compare_pronunciations
    to produce a better assertion message including classification, segment_relation,
    and segment_distance.
    """
    if left == right:
        return

    message_parts = [
        f"text: {text}",
        f"{left_name}: {left!r}",
        f"{right_name}: {right!r}",
    ]

    if isinstance(left, str) and isinstance(right, str):
        module = _import_phonodist()
        if module is not None:
            try:
                result = module.compare_pronunciations(
                    left, right, language=language
                )
                message_parts.extend([
                    f"classification: {result.classification}",
                    f"segment_relation: {result.segment_relation}",
                    f"segment_distance: {result.segmental.distance}",
                    f"stress_equal: {result.stress_equal}",
                ])
            except Exception as error:
                message_parts.append(f"phonodist_error: {error}")

    raise AssertionError("\n".join(message_parts))
