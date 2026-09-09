from __future__ import annotations


def normalize_language_tag(value: str) -> str:
    """Normalize locale spelling without claiming full BCP-47 validation."""
    if not isinstance(value, str):
        raise TypeError("language tag must be a string")
    return value.casefold().replace("_", "-")


def is_lexicon_language_compatible(profile_language: str, asset_language: str) -> bool:
    profile = normalize_language_tag(profile_language)
    asset = normalize_language_tag(asset_language)
    if asset == profile:
        return True
    return "-" not in asset and asset == profile.split("-", 1)[0]
