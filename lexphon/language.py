from __future__ import annotations


def normalize_language_tag(value: str) -> str:
    """Normalize locale spelling without claiming full BCP-47 validation."""
    if not isinstance(value, str):
        raise TypeError("language tag must be a string")
    return value.casefold().replace("_", "-")
