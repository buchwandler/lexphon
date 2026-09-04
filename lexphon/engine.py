from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any

import g2lex

from .alphabets import to_ipa
from .errors import LexiconNotUsableError, UnsupportedAlphabetError
from .fallback import EspeakFallback, Fallback
from .models import PhonemizationResult, PronunciationToken
from .profiles import LanguageProfile, ProfileRegistry
from .store import DataStore
from .tokenizer import tokenize


@dataclass(slots=True)
class _Layer:
    identifier: str
    encoding: str
    lexicon: Any


def _normalize_language(language: object) -> str:
    if not isinstance(language, str):
        return ""
    return language.casefold().replace("_", "-")


class Phonemizer:
    """Generic lexicon-first phonemizer returning normalized IPA."""

    def __init__(
        self,
        language: str,
        *,
        lexicons: tuple[str, ...] | list[str] | None = None,
        store: DataStore | None = None,
        profiles: ProfileRegistry | None = None,
        fallback: Fallback | str | None = None,
    ):
        self.store = store or DataStore()
        self.profile: LanguageProfile = (profiles or ProfileRegistry()).resolve(language)
        self.language = self.profile.language
        identifiers = tuple(lexicons) if lexicons is not None else self.profile.default_lexicons
        self.layers: list[_Layer] = []
        try:
            for identifier in identifiers:
                metadata = self.store.metadata(identifier)
                kind = metadata.get("kind")
                if kind != "pronunciation":
                    raise LexiconNotUsableError(
                        f"lexicon {identifier!r} has kind {kind!r}; only pronunciation lexica can be layers"
                    )
                if _normalize_language(metadata.get("language")) != _normalize_language(
                    self.profile.language
                ):
                    raise LexiconNotUsableError(
                        f"lexicon {identifier!r} language {metadata.get('language')!r} is not compatible "
                        f"with profile {self.profile.language!r}"
                    )
                encoding = metadata.get("phoneme_encoding")
                if not isinstance(encoding, str) or encoding.casefold() == "none":
                    raise LexiconNotUsableError(
                        f"lexicon {identifier!r} has no pronunciation alphabet and cannot be a layer"
                    )
                if encoding.casefold().replace("-", "") not in {
                    "ipa",
                    "unicodeipa",
                    "arpabet",
                    "cmu",
                    "cmudict",
                }:
                    raise UnsupportedAlphabetError(
                        f"unsupported pronunciation encoding {encoding!r} for {identifier!r}"
                    )
                self.layers.append(
                    _Layer(
                        identifier=identifier,
                        encoding=encoding,
                        lexicon=g2lex.open(self.store.path(identifier)),
                    )
                )
            if fallback == "espeak":
                self.fallback: Fallback | None = EspeakFallback()
            elif fallback is None:
                self.fallback = None
            elif isinstance(fallback, str):
                raise ValueError(f"unknown fallback: {fallback}")
            else:
                self.fallback = fallback
        except Exception:
            for layer in self.layers:
                layer.lexicon.close()
            raise
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("phonemizer is closed")

    def lookup(self, token: str, *, tag: str | None = None) -> PronunciationToken:
        self._ensure_open()
        candidates = self.profile.candidates(token)
        for layer in self.layers:
            for candidate in candidates:
                value = layer.lexicon.get(candidate, None)
                if value is None:
                    continue
                variants = g2lex.pronunciation_variants(value, tag=tag)
                if not variants:
                    continue
                ipa_variants = tuple(to_ipa(item, layer.encoding) for item in variants)
                return PronunciationToken(
                    text=token,
                    pronunciation=ipa_variants[0],
                    source="lexicon",
                    lexicon_id=layer.identifier,
                    matched_key=candidate,
                    source_encoding=layer.encoding,
                    variants=ipa_variants,
                    selector_tag=tag,
                )
        if self.fallback is not None:
            value = self.fallback.phonemize(token, self.language)
            if value:
                value = to_ipa(value, "ipa")
                return PronunciationToken(
                    text=token,
                    pronunciation=value,
                    source="espeak" if isinstance(self.fallback, EspeakFallback) else "fallback",
                    source_encoding="ipa",
                    variants=(value,),
                    selector_tag=tag,
                )
        return PronunciationToken(
            text=token, pronunciation=None, source="unknown", selector_tag=tag
        )

    def lookup_prefixes(
        self,
        text: str,
        *,
        position: int = 0,
        tag: str | None = None,
    ) -> tuple[PronunciationToken, ...]:
        """Return known pronunciation layers matching prefixes at ``position``.

        Results are ordered by layer precedence and then longest match first.
        Only exact dictionary keys are returned; fallback providers are not
        consulted for prefix matching.
        """
        self._ensure_open()
        if not isinstance(text, str) or position < 0 or position >= len(text):
            return ()
        matches: list[PronunciationToken] = []
        seen: set[str] = set()
        for layer in self.layers:
            for candidate in reversed(layer.lexicon.prefixes(text, position)):
                if candidate in seen:
                    continue
                value = layer.lexicon.get(candidate, None)
                if value is None:
                    continue
                variants = g2lex.pronunciation_variants(value, tag=tag)
                if not variants:
                    continue
                ipa_variants = tuple(to_ipa(item, layer.encoding) for item in variants)
                matches.append(
                    PronunciationToken(
                        text=candidate,
                        pronunciation=ipa_variants[0],
                        source="lexicon",
                        lexicon_id=layer.identifier,
                        matched_key=candidate,
                        source_encoding=layer.encoding,
                        variants=ipa_variants,
                        selector_tag=tag,
                    )
                )
                seen.add(candidate)
        return tuple(matches)


    def phonemize_tokens(self, text: str, *, tag: str | None = None) -> PhonemizationResult:
        self._ensure_open()
        tokens: list[PronunciationToken] = []
        for token, punctuation in tokenize(text):
            if punctuation:
                tokens.append(
                    PronunciationToken(
                        text=token, pronunciation=None, source="literal", punctuation=True
                    )
                )
            else:
                tokens.append(self.lookup(token, tag=tag))
        return PhonemizationResult(text=text, language=self.language, tokens=tuple(tokens))

    def phonemize(
        self,
        text: str,
        *,
        tag: str | None = None,
        unknown: str = "error",
        punctuation: str = "keep",
    ) -> str:
        return self.phonemize_tokens(text, tag=tag).render(unknown=unknown, punctuation=punctuation)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for layer in self.layers:
            layer.lexicon.close()

    def __enter__(self):
        self._ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
