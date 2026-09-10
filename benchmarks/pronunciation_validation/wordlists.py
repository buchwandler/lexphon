"""Curated ranked word-list sources and deterministic cache/adapters."""

from __future__ import annotations

import hashlib
import urllib.request
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .model import RankedWord, WordListResult, WordListSpec

_SOURCE_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/{language}/{language}_50k.txt"
_LANGUAGES = (
    "ar", "az", "bg", "ca", "ceb", "cs", "de", "el", "en", "es", "fr", "ga", "he", "hi",
    "hu", "hy", "id", "it", "ja", "ko", "ku", "la", "lt", "lv", "mr", "ms", "nl",
    "pl", "pt", "ro", "ru", "sv", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi", "zh",
)

WORD_LISTS = {
    language: WordListSpec(
        id=f"frequencywords-2018-{language}",
        language=language,
        url=_SOURCE_URL.format(language=language),
        revision="2018",
        format="word_count",
        license_note="FrequencyWords repository data; consult its upstream license and attribution terms.",
    )
    for language in _LANGUAGES
}


def word_list_key_for(language: str) -> str:
    return language.casefold().replace("_", "-").split("-", 1)[0]


def resolve_word_list(key: str | None, language: str) -> WordListSpec:
    resolved = key or word_list_key_for(language)
    try:
        return WORD_LISTS[resolved.casefold()]
    except KeyError as error:
        raise ValueError(f"no curated word list is configured for language {resolved!r}") from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_word(value: str) -> str | None:
    word = value.strip()
    if not word or any(char.isspace() for char in word) or any(char in word for char in "0123456789"):
        return None
    return word


def _parse_rows(lines: Iterable[str], source_format: str) -> tuple[list[RankedWord], int, int]:
    entries: dict[str, tuple[int, int]] = {}
    frequency_format = source_format in {"word_count", "frequency", "word_frequency"}
    rejected = 0
    rejected_phrases = 0
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue
        if source_format in {"word", "one_word_per_line", "words"}:
            word = line
            rank = line_number
        elif source_format in {"ranked_tsv", "ranked", "rank_tab_word"}:
            fields = line.split("\t", 1)
            if len(fields) != 2:
                rejected += 1
                continue
            try:
                rank = int(fields[0].strip())
            except ValueError:
                if fields[0].strip().casefold() == "rank":
                    continue
                rejected += 1
                continue
            word = fields[1]
        elif frequency_format:
            fields = line.split()
            if len(fields) != 2:
                rejected += 1
                continue
            word = fields[0]
            try:
                count = int(fields[1])
            except ValueError:
                rejected += 1
                continue
            rank = -count
        else:
            raise ValueError(f"unsupported word-list format {source_format!r}")

        cleaned = _clean_word(word)
        if cleaned is None or (not frequency_format and rank < 1):
            rejected += 1
            if cleaned is None and any(char.isspace() for char in word.strip()):
                rejected_phrases += 1
            continue
        previous = entries.get(cleaned)
        if previous is None or rank < previous[0]:
            entries[cleaned] = (rank, line_number)

    if frequency_format:
        ordered = sorted(entries.items(), key=lambda item: (item[1][0], item[1][1], item[0]))
        words = [RankedWord(index, word) for index, (word, _) in enumerate(ordered, 1)]
    else:
        words = [RankedWord(rank, word) for word, (rank, _) in entries.items()]
        words.sort(key=lambda item: (item.rank, entries[item.word][1], item.word))
    return words, rejected, rejected_phrases


def load_ranked_words(
    path: Path,
    *,
    limit: int | None = None,
    min_rank: int | None = None,
    max_rank: int | None = None,
) -> list[RankedWord]:
    """Load adapted ``rank<TAB>word`` rows with deterministic de-duplication."""
    entries: dict[str, tuple[int, int]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line:
                continue
            fields = line.split("\t", 1) if "\t" in line else line.split(None, 1)
            if len(fields) != 2:
                if line.casefold() in {"rank word", "rank\tword"}:
                    continue
                raise ValueError(f"{path}:{line_number}: expected rank and word")
            raw_rank, word = fields
            if raw_rank.strip().casefold() == "rank" and word.strip().casefold() == "word":
                continue
            try:
                rank = int(raw_rank.strip())
            except ValueError as error:
                raise ValueError(f"{path}:{line_number}: invalid rank {raw_rank!r}") from error
            word = word.strip()
            if rank < 1:
                raise ValueError(f"{path}:{line_number}: rank must be positive")
            if not word:
                continue
            if min_rank is not None and rank < min_rank:
                continue
            if max_rank is not None and rank > max_rank:
                continue
            previous = entries.get(word)
            if previous is None or rank < previous[0]:
                entries[word] = (rank, previous[1] if previous else line_number)
    words = [RankedWord(rank, word) for word, (rank, _) in entries.items()]
    words.sort(key=lambda item: (item.rank, entries[item.word][1], item.word))
    return words if limit is None else words[:limit]


def _adapt_payload(payload: bytes, source: WordListSpec, target: Path) -> tuple[Path, int, int]:
    lines = payload.decode("utf-8-sig").splitlines()
    words, rejected, rejected_phrases = _parse_rows(lines, source.format)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(f"{word.rank}\t{word.word}\n" for word in words), encoding="utf-8")
    return target, rejected, rejected_phrases


def _download(source: WordListSpec, raw_path: Path) -> bytes:
    try:
        with urllib.request.urlopen(source.url, timeout=60) as response:
            payload = response.read()
    except Exception as error:
        raise RuntimeError(f"unable to download word list {source.id} from {source.url}: {error}") from error
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(payload)
    return payload


def ensure_word_list(
    source: WordListSpec,
    root: Path,
    *,
    refresh: bool = False,
    offline: bool = False,
) -> WordListResult:
    """Resolve a source into the shared adapted cache and return provenance."""
    directory = root / source.id
    raw_path = directory / "source.txt"
    ranked_path = directory / "ranked.tsv"
    if refresh or not raw_path.is_file() or not ranked_path.is_file():
        if offline:
            raise RuntimeError(f"word-list cache miss for {source.id!r} in offline mode")
        payload = _download(source, raw_path)
        _, rejected, rejected_phrases = _adapt_payload(payload, source, ranked_path)
        retrieved_at = datetime.now(timezone.utc).isoformat()
    else:
        rejected = rejected_phrases = 0
        retrieved_at = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc).isoformat()
    words = tuple(load_ranked_words(ranked_path))
    return WordListResult(
        words=words,
        spec=source,
        source_path=ranked_path,
        download_sha256=_sha256(raw_path) if raw_path.is_file() else None,
        ranked_sha256=_sha256(ranked_path),
        retrieved_at=retrieved_at,
        rejected_rows=rejected,
        rejected_phrases=rejected_phrases,
    )


def adapt_word_list(payload: str | bytes, source_format: str) -> list[RankedWord]:
    """Adapt raw text in tests and integrations without touching the filesystem."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8-sig")
    return _parse_rows(payload.splitlines(), source_format)[0]
