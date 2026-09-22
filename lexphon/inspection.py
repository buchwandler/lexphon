from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import g2lex

from .errors import UnknownWordError
from .layers import OpenedLexiconLayer, open_installed_pronunciation_layer
from .profiles import LanguageProfile, ProfileRegistry
from .store import DataStore
from .tokenizer import tokenize

StoredValueKind = Literal["scalar", "list", "tagged", "word_only"]
SelectionMode = Literal["exact", "default", "untagged", "unresolved"]
RawSource = Literal["lexicon", "unknown", "literal"]


@dataclass(frozen=True, slots=True)
class StoredSelectorValue:
    tag: str | None
    values: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class StoredValueInspection:
    kind: StoredValueKind
    stored: tuple[StoredSelectorValue, ...]
    selected_tag: str | None
    selected_via: SelectionMode
    selected_values: tuple[str, ...]

    @property
    def available_tags(self) -> tuple[str, ...]:
        return tuple(item.tag for item in self.stored if item.tag is not None)


@dataclass(frozen=True, slots=True)
class LexiconEntryInspection:
    query: str
    language: str
    lexicon_id: str
    matched_key: str
    source_encoding: str
    kind: StoredValueKind
    stored: tuple[StoredSelectorValue, ...]
    requested_tag: str | None
    selected_tag: str | None
    selected_via: SelectionMode
    selected_values: tuple[str, ...]

    @property
    def available_tags(self) -> tuple[str, ...]:
        return tuple(item.tag for item in self.stored if item.tag is not None)


@dataclass(frozen=True, slots=True)
class RawPronunciationVariant:
    pronunciation: str
    source_pronunciation: str


@dataclass(frozen=True, slots=True)
class RawPronunciationToken:
    text: str
    source: RawSource
    variants: tuple[RawPronunciationVariant, ...] = ()
    lexicon_id: str | None = None
    matched_key: str | None = None
    source_encoding: str | None = None
    selector_tag: str | None = None
    punctuation: bool = False

    @property
    def pronunciation(self) -> str | None:
        return self.variants[0].pronunciation if self.variants else None

    @property
    def source_pronunciation(self) -> str | None:
        return self.variants[0].source_pronunciation if self.variants else None

    @property
    def known(self) -> bool:
        return bool(self.variants)


@dataclass(frozen=True, slots=True)
class RawPhonemizationResult:
    text: str
    language: str
    tokens: tuple[RawPronunciationToken, ...]

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


def _selector_values(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return (value,)
    assert isinstance(value, tuple)
    return value


def inspect_value(
    value: object,
    *,
    tag: str | None,
    default_tag: str = "DEFAULT",
) -> StoredValueInspection:
    if value is g2lex.WORD_ONLY:
        return StoredValueInspection("word_only", (), None, "unresolved", ())

    if isinstance(value, str):
        values = (value,)
        return StoredValueInspection(
            "scalar", (StoredSelectorValue(None, values),), None, "untagged", values
        )

    if isinstance(value, tuple):
        return StoredValueInspection(
            "list", (StoredSelectorValue(None, value),), None, "untagged", value
        )

    if not isinstance(value, g2lex.TaggedValue):
        raise TypeError(f"unsupported G2Lex value: {type(value)!r}")

    stored = tuple(
        StoredSelectorValue(selector_tag, _selector_values(selector_value))
        for selector_tag, selector_value in value.items
    )
    selected_tag: str | None = None
    selected_via: SelectionMode = "unresolved"
    selected_values: tuple[str, ...] = ()
    selected_source: object | None = None
    if tag is not None:
        for selector_tag, selector_value in value.items:
            if selector_tag == tag:
                selected_tag = selector_tag
                selected_via = "exact"
                selected_source = selector_value
                break
    if selected_via == "unresolved":
        for selector_tag, selector_value in value.items:
            if selector_tag == default_tag:
                selected_tag = selector_tag
                selected_via = "default"
                selected_source = selector_value
                break
    if selected_via != "unresolved":
        selected_values = _selector_values(selected_source) or ()
    return StoredValueInspection("tagged", stored, selected_tag, selected_via, selected_values)


def _inspection_for_layer(
    query: str,
    language: str,
    lexicon_id: str,
    layer: OpenedLexiconLayer,
    value: object,
    *,
    tag: str | None,
) -> LexiconEntryInspection:
    inspected = inspect_value(value, tag=tag)
    return LexiconEntryInspection(
        query=query,
        language=language,
        lexicon_id=lexicon_id,
        matched_key="",
        source_encoding=layer.encoding,
        kind=inspected.kind,
        stored=inspected.stored,
        requested_tag=tag,
        selected_tag=inspected.selected_tag,
        selected_via=inspected.selected_via,
        selected_values=inspected.selected_values,
    )


def inspect_entry(
    word: str,
    *,
    language: str,
    lexicon_id: str,
    tag: str | None = None,
    store: DataStore | None = None,
    profiles: ProfileRegistry | None = None,
) -> LexiconEntryInspection | None:
    store = store if store is not None else DataStore()
    profile = (profiles or ProfileRegistry()).resolve(language)
    layer = open_installed_pronunciation_layer(store, profile.language, lexicon_id)
    try:
        for candidate in profile.candidates(word):
            value = layer.lexicon.get(candidate, None)
            if value is None:
                continue
            result = _inspection_for_layer(
                word,
                profile.language,
                lexicon_id,
                layer,
                value,
                tag=tag,
            )
            return LexiconEntryInspection(
                query=result.query,
                language=result.language,
                lexicon_id=result.lexicon_id,
                matched_key=candidate,
                source_encoding=result.source_encoding,
                kind=result.kind,
                stored=result.stored,
                requested_tag=result.requested_tag,
                selected_tag=result.selected_tag,
                selected_via=result.selected_via,
                selected_values=result.selected_values,
            )
    finally:
        layer.lexicon.close()
    return None


class OpaqueDisplayResolver:
    def __init__(
        self,
        language: str,
        *,
        lexicons: Sequence[str],
        store: DataStore | None = None,
        profiles: ProfileRegistry | None = None,
    ) -> None:
        self.store = store if store is not None else DataStore()
        self.profile: LanguageProfile = (profiles or ProfileRegistry()).resolve(language)
        self.language = self.profile.language
        self.layers: list[OpenedLexiconLayer] = []
        try:
            for identifier in lexicons:
                self.layers.append(
                    open_installed_pronunciation_layer(self.store, self.language, identifier)
                )
        except Exception:
            self.close()
            raise
        self._closed = False

    def _ensure_open(self) -> None:
        if self._closed:
            raise ValueError("opaque display resolver is closed")

    def lookup(self, token: str, *, tag: str | None = None) -> RawPronunciationToken | None:
        self._ensure_open()
        for layer in self.layers:
            for candidate in self.profile.candidates(token):
                value = layer.lexicon.get(candidate, None)
                if value is None:
                    continue
                inspected = inspect_value(value, tag=tag)
                if not inspected.selected_values:
                    continue
                variants = tuple(
                    RawPronunciationVariant(value, value) for value in inspected.selected_values
                )
                return RawPronunciationToken(
                    text=token,
                    source="lexicon",
                    variants=variants,
                    lexicon_id=layer.identifier,
                    matched_key=candidate,
                    source_encoding=layer.encoding,
                    selector_tag=tag,
                )
        return None

    def phonemize_tokens(self, text: str, *, tag: str | None = None) -> RawPhonemizationResult:
        self._ensure_open()
        tokenized = tokenize(text)
        tokens: list[RawPronunciationToken] = []
        for token, punctuation in tokenized:
            if punctuation:
                tokens.append(RawPronunciationToken(text=token, source="literal", punctuation=True))
                continue
            result = self.lookup(token, tag=tag)
            tokens.append(result or RawPronunciationToken(text=token, source="unknown"))
        return RawPhonemizationResult(text=text, language=self.language, tokens=tuple(tokens))

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        for layer in self.layers:
            layer.lexicon.close()

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
