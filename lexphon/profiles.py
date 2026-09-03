from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from importlib.resources import files
from typing import Literal, cast

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


_APOSTROPHE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‛": "'",
        "＇": "'",
        "`": "'",
        "´": "'",
    }
)


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    language: str
    aliases: tuple[str, ...]
    default_lexicons: tuple[str, ...]
    case_candidates: tuple[str, ...]
    unicode_normalization: str = "NFC"
    apostrophe_normalization: str = "none"

    def _normalize(self, value: str) -> str:
        if self.unicode_normalization.casefold() == "none":
            normalized = value
        else:
            form = cast(
                Literal["NFC", "NFD", "NFKC", "NFKD"], self.unicode_normalization.upper()
            )
            normalized = unicodedata.normalize(form, value)
        if self.apostrophe_normalization.casefold() == "ascii":
            normalized = normalized.translate(_APOSTROPHE_MAP)
        return normalized

    def candidates(self, token: str) -> tuple[str, ...]:
        token = self._normalize(token)
        values: list[str] = []
        for policy in self.case_candidates:
            if policy == "exact":
                candidate = token
            elif policy == "lower":
                candidate = token.lower()
            elif policy == "casefold":
                candidate = token.casefold()
            elif policy == "title":
                candidate = token.title()
            elif policy == "normalized":
                candidate = token
            else:
                continue
            candidate = self._normalize(candidate)
            if candidate not in values:
                values.append(candidate)
        return tuple(values)


class ProfileRegistry:
    def __init__(self, profiles: tuple[LanguageProfile, ...] | None = None):
        self.profiles = profiles or self._load_builtin()

    @staticmethod
    def _load_builtin() -> tuple[LanguageProfile, ...]:
        raw = tomllib.loads(files("lexphon").joinpath("profiles.toml").read_text(encoding="utf-8"))
        result: list[LanguageProfile] = []
        for language, values in raw.get("profile", {}).items():
            result.append(
                LanguageProfile(
                    language=language,
                    aliases=tuple(values.get("aliases", ())),
                    default_lexicons=tuple(values.get("default_lexicons", ())),
                    case_candidates=tuple(values.get("case_candidates", ("exact", "lower"))),
                    unicode_normalization=str(values.get("unicode_normalization", "NFC")),
                    apostrophe_normalization=str(values.get("apostrophe_normalization", "none")),
                )
            )
        return tuple(result)

    def resolve(self, language: str) -> LanguageProfile:
        key = language.casefold().replace("_", "-")
        for profile in self.profiles:
            names = (profile.language, *profile.aliases)
            if key in {name.casefold().replace("_", "-") for name in names}:
                return profile
        return LanguageProfile(
            language=language,
            aliases=(),
            default_lexicons=(),
            case_candidates=("exact", "lower", "title"),
            unicode_normalization="NFC",
            apostrophe_normalization="none",
        )
