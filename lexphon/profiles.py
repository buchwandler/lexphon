from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class LanguageProfile:
    language: str
    aliases: tuple[str, ...]
    default_lexicons: tuple[str, ...]
    case_candidates: tuple[str, ...]

    def candidates(self, token: str) -> tuple[str, ...]:
        values: list[str] = []
        for policy in self.case_candidates:
            if policy == "exact":
                candidate = token
            elif policy == "lower":
                candidate = token.lower()
            elif policy == "title":
                candidate = token[:1].upper() + token[1:].lower() if token else token
            else:
                continue
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
                )
            )
        return tuple(result)

    def resolve(self, language: str) -> LanguageProfile:
        key = language.casefold().replace("_", "-")
        for profile in self.profiles:
            names = (profile.language, *profile.aliases)
            if key in {name.casefold().replace("_", "-") for name in names}:
                return profile
        return LanguageProfile(language=language, aliases=(), default_lexicons=(), case_candidates=("exact", "lower", "title"))
