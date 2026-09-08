from __future__ import annotations

import unicodedata


def _is_word_base(value: str) -> bool:
    return value != "_" and unicodedata.category(value)[0] in {"L", "N"}


def _is_combining_mark(value: str) -> bool:
    return unicodedata.category(value) in {"Mn", "Mc", "Me"}


def tokenize(text: str) -> tuple[tuple[str, bool], ...]:
    result: list[tuple[str, bool]] = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue

        start = position
        if _is_word_base(text[position]):
            position += 1
            while position < len(text):
                value = text[position]
                if _is_word_base(value) or _is_combining_mark(value):
                    position += 1
                    continue
                if (
                    value in {"'", "’", "-"}
                    and position + 1 < len(text)
                    and _is_word_base(text[position + 1])
                ):
                    position += 1
                    continue
                break
        else:
            position += 1

        token = text[start:position]
        punctuation = not any(ch.isalnum() for ch in token)
        result.append((token, punctuation))
    return tuple(result)
