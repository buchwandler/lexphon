from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import g2lex

from .alphabets import normalize_pronunciation
from .errors import LexiconNotUsableError, LexphonError, UnsupportedAlphabetError
from .fallback import Fallback, FallbackPronunciation, create_fallback
from .models import PhonemizationResult, PronunciationToken, PronunciationVariant
from .profiles import LanguageProfile, ProfileRegistry
from .pronunciation import parse_pronunciation_controls
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


def _normalize_variants(
    raw_variants: tuple[str, ...],
    encoding: str,
) -> tuple[PronunciationVariant, ...]:
    return tuple(
        PronunciationVariant(
            pronunciation=result.pronunciation,
            source_pronunciation=result.source_pronunciation,
            language_markers=result.language_markers,
        )
        for result in (normalize_pronunciation(value, encoding) for value in raw_variants)
    )


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
            self._fallback_name: str | None = None
            self.fallback: Fallback | None = None
            if isinstance(fallback, str):
                if fallback not in {"espeak", "goruut"}:
                    raise ValueError(f"unknown fallback: {fallback}")
                self._fallback_name = fallback
            elif fallback is not None:
                self.fallback = fallback
        except Exception:
            for layer in self.layers:
                layer.lexicon.close()
            raise
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("phonemizer is closed")

    def _get_fallback(self) -> Fallback | None:
        if self.fallback is not None:
            return self.fallback
        if self._fallback_name is None:
            return None
        try:
            self.fallback = create_fallback(self._fallback_name)
        except LexphonError:
            return None
        return self.fallback

    def _coerce_fallback_value(
        self,
        fallback: Fallback,
        value: FallbackPronunciation | str | None,
    ) -> FallbackPronunciation | None:
        if isinstance(value, FallbackPronunciation):
            source = value.source_pronunciation or value.pronunciation
            parsed = parse_pronunciation_controls(" ".join(source.split()))
            return FallbackPronunciation(
                pronunciation=parsed.pronunciation,
                provider=value.provider,
                source_pronunciation=source,
                language_markers=parsed.language_markers,
                source_encoding=value.source_encoding,
                provider_language=value.provider_language or self.language,
            )
        if not isinstance(value, str) or not value:
            return None
        parsed = parse_pronunciation_controls(" ".join(value.split()))
        return FallbackPronunciation(
            pronunciation=parsed.pronunciation,
            provider=getattr(fallback, "name", fallback.__class__.__name__.lower()),
            source_pronunciation=value,
            language_markers=parsed.language_markers,
            provider_language=self.language,
        )

    def _lookup_fallback(self, token: str) -> FallbackPronunciation | None:
        fallback = self._get_fallback()
        if fallback is None:
            return None
        try:
            value = fallback.phonemize(token, self.language)
        except Exception:  # noqa: BLE001
            return None
        return self._coerce_fallback_value(fallback, value)

    def _fallback_token(
        self,
        token: str,
        tag: str | None,
        result: FallbackPronunciation,
    ) -> PronunciationToken:
        variant = PronunciationVariant(
            pronunciation=result.pronunciation,
            source_pronunciation=result.source_pronunciation,
            language_markers=result.language_markers,
        )
        return PronunciationToken(
            text=token,
            pronunciation=result.pronunciation,
            source="fallback",
            source_encoding=result.source_encoding,
            variants=(result.pronunciation,),
            selector_tag=tag,
            variant_details=(variant,),
            provider=result.provider,
        )

    def lookup_lexicon(
        self,
        token: str,
        *,
        tag: str | None = None,
    ) -> PronunciationToken | None:
        """Look up a token in the configured lexicon layers only."""
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
                variant_details = _normalize_variants(variants, layer.encoding)
                ipa_variants = tuple(detail.pronunciation for detail in variant_details)
                return PronunciationToken(
                    text=token,
                    pronunciation=ipa_variants[0],
                    source="lexicon",
                    lexicon_id=layer.identifier,
                    matched_key=candidate,
                    source_encoding=layer.encoding,
                    variants=ipa_variants,
                    selector_tag=tag,
                    variant_details=variant_details,
                )
        return None

    def lookup(self, token: str, *, tag: str | None = None) -> PronunciationToken:
        """Look up lexicon evidence first, then use the configured fallback."""
        self._ensure_open()
        lexical = self.lookup_lexicon(token, tag=tag)
        if lexical is not None:
            return lexical
        fallback = self._lookup_fallback(token)
        if fallback is not None:
            return self._fallback_token(token, tag, fallback)
        return PronunciationToken(
            text=token, pronunciation=None, source="unknown", selector_tag=tag
        )

    def lookup_many(
        self,
        tokens: Sequence[str],
        *,
        tag: str | None = None,
    ) -> tuple[PronunciationToken, ...]:
        """Look up tokens with one batch call to fallback providers when available."""
        self._ensure_open()
        values = tuple(tokens)
        results: list[PronunciationToken | None] = [
            self.lookup_lexicon(token, tag=tag) for token in values
        ]
        missing = tuple(index for index, result in enumerate(results) if result is None)
        fallback = self._get_fallback()
        if missing and fallback is not None:
            batch = getattr(fallback, "phonemize_many", None)
            try:
                if callable(batch):
                    raw_values = batch(tuple(values[index] for index in missing), self.language)
                else:
                    raw_values = tuple(
                        fallback.phonemize(values[index], self.language) for index in missing
                    )
            except Exception:  # noqa: BLE001
                raw_values = ()
            if len(raw_values) == len(missing):
                for index, raw_value in zip(missing, raw_values):
                    normalized = self._coerce_fallback_value(fallback, raw_value)
                    if normalized is not None:
                        results[index] = self._fallback_token(values[index], tag, normalized)
        return tuple(
            result
            if result is not None
            else PronunciationToken(
                text=values[index], pronunciation=None, source="unknown", selector_tag=tag
            )
            for index, result in enumerate(results)
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
            prefixes = getattr(layer.lexicon, "prefixes", None)
            if callable(prefixes):
                candidates = prefixes(text, position)
            else:
                candidates = tuple(key for key in layer.lexicon if text.startswith(key, position))
            for candidate in sorted(candidates, key=len, reverse=True):
                if candidate in seen:
                    continue
                value = layer.lexicon.get(candidate, None)
                if value is None:
                    continue
                variants = g2lex.pronunciation_variants(value, tag=tag)
                if not variants:
                    continue
                variant_details = _normalize_variants(variants, layer.encoding)
                ipa_variants = tuple(detail.pronunciation for detail in variant_details)
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
                        variant_details=variant_details,
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
