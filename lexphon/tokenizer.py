from __future__ import annotations

import re

_TOKEN = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> tuple[tuple[str, bool], ...]:
    result: list[tuple[str, bool]] = []
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        punctuation = not any(ch.isalnum() for ch in token)
        result.append((token, punctuation))
    return tuple(result)
