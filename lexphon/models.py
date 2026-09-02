from __future__ import annotations

from dataclasses import dataclass

from .errors import UnknownWordError


@dataclass(frozen=True, slots=True)
class PronunciationToken:
    text: str
    pronunciation: str | None
    source: str
    alphabet: str = "ipa"
    lexicon_id: str | None = None
    matched_key: str | None = None
    source_encoding: str | None = None
    variants: tuple[str, ...] = ()
    selector_tag: str | None = None
    punctuation: bool = False

    @property
    def known(self) -> bool:
        return self.pronunciation is not None


@dataclass(frozen=True, slots=True)
class PhonemizationResult:
    text: str
    language: str
    tokens: tuple[PronunciationToken, ...]

    @property
    def unknown_tokens(self) -> tuple[PronunciationToken, ...]:
        return tuple(token for token in self.tokens if not token.punctuation and not token.known)

    def render(self, *, unknown: str = "error", punctuation: str = "keep") -> str:
        if unknown not in {"error", "keep", "skip"}:
            raise ValueError("unknown must be error, keep, or skip")
        if punctuation not in {"keep", "drop"}:
            raise ValueError("punctuation must be keep or drop")
        parts: list[str] = []
        for token in self.tokens:
            if token.punctuation:
                if punctuation == "keep" and parts:
                    parts[-1] = parts[-1] + token.text
                elif punctuation == "keep":
                    parts.append(token.text)
                continue
            if token.pronunciation is not None:
                parts.append(token.pronunciation)
                continue
            if unknown == "error":
                raise UnknownWordError(f"no pronunciation for {token.text!r}")
            if unknown == "keep":
                parts.append(token.text)
        return " ".join(parts)
