from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import g2lex

from .alphabets import normalize_pronunciation
from .errors import (
    LexiconNotUsableError,
    ProviderError,
    ProviderExecutionError,
    ProviderOutputError,
    UnsupportedAlphabetError,
)
from .language import is_lexicon_language_compatible, normalize_language_tag
from .models import PhonemizationResult, PronunciationToken, PronunciationVariant
from .profiles import LanguageProfile, ProfileRegistry
from .providers import BatchPronunciationProvider, PronunciationProvider, create_provider
from .store import DataStore
from .tokenizer import tokenize


@dataclass(slots=True)
class _Layer:
    identifier: str
    encoding: str
    lexicon: Any


def _normalize_variants(
    raw_variants: tuple[str, ...],
    encoding: str,
) -> tuple[PronunciationVariant, ...]:
    return tuple(normalize_pronunciation(value, encoding) for value in raw_variants)


class Phonemizer:
    """Generic lexicon-first phonemizer returning normalized IPA."""

    def __init__(
        self,
        language: str,
        *,
        lexicons: tuple[str, ...] | list[str] | None = None,
        store: DataStore | None = None,
        profiles: ProfileRegistry | None = None,
        fallback: PronunciationProvider | str | None = None,
    ):
        self.store = store or DataStore()
        self.profile: LanguageProfile = (profiles or ProfileRegistry()).resolve(language)
        self.language = normalize_language_tag(self.profile.language)
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
                metadata_language = metadata.get("language")
                if not isinstance(metadata_language, str) or not is_lexicon_language_compatible(
                    self.language, metadata_language
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
            self._provider_name: str | None = None
            self.provider: PronunciationProvider | None = None
            self._owns_provider = False
            if isinstance(fallback, str):
                if fallback not in {"espeak", "goruut"}:
                    raise ValueError(f"unknown provider: {fallback}")
                self._provider_name = fallback
            elif fallback is not None:
                self.provider = fallback
        except Exception:
            for layer in self.layers:
                layer.lexicon.close()
            raise
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("phonemizer is closed")

    def _get_provider(self) -> PronunciationProvider | None:
        if self.provider is not None:
            return self.provider
        if self._provider_name is None:
            return None
        self.provider = create_provider(self._provider_name)
        self._owns_provider = True
        return self.provider

    def _provider_name_for(self, provider: PronunciationProvider) -> str:
        name = getattr(provider, "name", None)
        if not isinstance(name, str) or not name:
            raise ProviderOutputError("provider must declare a non-empty name")
        return name

    def _provider_encoding_for(self, provider: PronunciationProvider) -> str:
        encoding = getattr(provider, "source_encoding", None)
        if not isinstance(encoding, str) or not encoding:
            raise ProviderOutputError("provider must declare a non-empty source_encoding")
        return encoding

    def _normalize_provider_value(
        self,
        provider: PronunciationProvider,
        value: object,
    ) -> PronunciationVariant | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            name = self._provider_name_for(provider)
            raise ProviderOutputError(f"provider {name!r} returned malformed pronunciation output")
        try:
            return normalize_pronunciation(value, self._provider_encoding_for(provider))
        except UnsupportedAlphabetError as error:
            name = self._provider_name_for(provider)
            raise ProviderOutputError(
                f"provider {name!r} returned unsupported pronunciation output"
            ) from error

    def _call_provider(self, provider: PronunciationProvider, token: str) -> str | None:
        try:
            value = provider.phonemize(token, self.language)
        except ProviderError:
            raise
        except Exception as error:
            name = self._provider_name_for(provider)
            raise ProviderExecutionError(f"provider {name!r} execution failed: {error}") from error
        if value is not None and not isinstance(value, str):
            name = self._provider_name_for(provider)
            raise ProviderOutputError(f"provider {name!r} returned malformed pronunciation output")
        return value

    def _provider_token(
        self,
        token: str,
        tag: str | None,
        provider: PronunciationProvider,
        variant: PronunciationVariant,
    ) -> PronunciationToken:
        return PronunciationToken(
            text=token,
            source="provider",
            variants=(variant,),
            source_encoding=self._provider_encoding_for(provider),
            selector_tag=tag,
            provider=self._provider_name_for(provider),
            requested_language=self.language,
        )

    def _lexicon_result(
        self,
        *,
        token: str,
        layer: _Layer,
        matched_key: str,
        value: g2lex.LexiconValue,
        tag: str | None,
    ) -> PronunciationToken | None:
        variants = g2lex.pronunciation_variants(value, tag=tag)
        if not variants:
            return None
        normalized = _normalize_variants(variants, layer.encoding)
        return PronunciationToken(
            text=token,
            source="lexicon",
            variants=normalized,
            lexicon_id=layer.identifier,
            matched_key=matched_key,
            source_encoding=layer.encoding,
            selector_tag=tag,
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
                result = self._lexicon_result(
                    token=token,
                    layer=layer,
                    matched_key=candidate,
                    value=value,
                    tag=tag,
                )
                if result is not None:
                    return result
        return None

    def lookup(self, token: str, *, tag: str | None = None) -> PronunciationToken | None:
        """Look up a token in the lexicons, then use the configured provider."""
        self._ensure_open()
        lexical = self.lookup_lexicon(token, tag=tag)
        if lexical is not None:
            return lexical
        provider = self._get_provider()
        if provider is None:
            return None
        raw = self._call_provider(provider, token)
        variant = self._normalize_provider_value(provider, raw)
        if variant is None:
            return None
        return self._provider_token(token, tag, provider, variant)

    def lookup_many(
        self,
        tokens: Sequence[str],
        *,
        tag: str | None = None,
    ) -> tuple[PronunciationToken | None, ...]:
        """Look up tokens with optional real provider batching."""
        self._ensure_open()
        values = tuple(tokens)
        results: list[PronunciationToken | None] = [
            self.lookup_lexicon(token, tag=tag) for token in values
        ]
        missing = tuple(index for index, result in enumerate(results) if result is None)
        if not missing:
            return tuple(results)
        provider = self._get_provider()
        if provider is None:
            return tuple(results)

        if isinstance(provider, BatchPronunciationProvider):
            try:
                batch = provider.phonemize_many(
                    tuple(values[index] for index in missing), self.language
                )
            except ProviderError:
                raise
            except Exception as error:
                name = self._provider_name_for(provider)
                raise ProviderExecutionError(
                    f"provider {name!r} batch execution failed: {error}"
                ) from error
            if isinstance(batch, (str, bytes)) or not isinstance(batch, Sequence):
                name = self._provider_name_for(provider)
                raise ProviderOutputError(
                    f"provider {name!r} returned an invalid batch output; expected a sequence"
                )
            raw_values = tuple(batch)
            if len(raw_values) != len(missing):
                name = self._provider_name_for(provider)
                raise ProviderOutputError(
                    f"provider {name!r} returned {len(raw_values)} results for {len(missing)} inputs"
                )
        else:
            raw_values = tuple(self._call_provider(provider, values[index]) for index in missing)

        for index, raw_value in zip(missing, raw_values):
            variant = self._normalize_provider_value(provider, raw_value)
            if variant is not None:
                results[index] = self._provider_token(values[index], tag, provider, variant)
        return tuple(results)

    def lookup_prefixes(
        self,
        text: str,
        *,
        position: int = 0,
        tag: str | None = None,
    ) -> tuple[PronunciationToken, ...]:
        """Return known pronunciation layers matching prefixes at ``position``."""
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
                result = self._lexicon_result(
                    token=candidate,
                    layer=layer,
                    matched_key=candidate,
                    value=value,
                    tag=tag,
                )
                if result is not None:
                    matches.append(result)
                    seen.add(candidate)
        return tuple(matches)

    def phonemize_tokens(self, text: str, *, tag: str | None = None) -> PhonemizationResult:
        self._ensure_open()
        tokenized = tokenize(text)
        content = tuple(token for token, punctuation in tokenized if not punctuation)
        looked_up = iter(self.lookup_many(content, tag=tag))
        tokens: list[PronunciationToken] = []
        for token, punctuation in tokenized:
            if punctuation:
                tokens.append(PronunciationToken(text=token, source="literal", punctuation=True))
            else:
                result = next(looked_up)
                tokens.append(
                    result
                    if result is not None
                    else PronunciationToken(text=token, source="unknown")
                )
        return PhonemizationResult(text=text, language=self.language, tokens=tuple(tokens))

    def phonemize(
        self,
        text: str,
        *,
        tag: str | None = None,
        unknown: str = "error",
        punctuation: str = "keep",
    ) -> str:
        return self.phonemize_tokens(text, tag=tag).render(
            unknown=unknown,
            punctuation=punctuation,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for layer in self.layers:
            layer.lexicon.close()
        if self._owns_provider and self.provider is not None:
            close = getattr(self.provider, "close", None)
            if callable(close):
                close()

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
