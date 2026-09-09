#!/usr/bin/env python3
"""Developer-side validation of installed Lexphon pronunciation lexica."""
# ruff: noqa: I001

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import unicodedata
import urllib.request
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lexphon import DataStore, Phonemizer
from lexphon.alphabets import normalize_pronunciation
from lexphon.errors import (
    LexiconNotInstalledError,
    ProviderError,
    ProviderOutputError,
    ProviderUnavailableError,
)
from lexphon.providers import BatchPronunciationProvider, EspeakProvider, PronunciationProvider


STRESS_MARKS = frozenset(("ˈ", "ˌ"))
TIE_BARS = frozenset(("͡", "͜"))
BAND_LIMITS = (100, 1_000, 10_000, 50_000)
SEVERITY = {
    "match": 0,
    "very_close": 1,
    "different": 2,
    "inspect": 3,
    "strong_disagreement": 4,
}


@dataclass(frozen=True, slots=True)
class RankedWord:
    rank: int
    word: str


@dataclass(frozen=True, slots=True)
class DistanceResult:
    edits: int
    normalized: float


def load_ranked_words(
    path: Path,
    *,
    limit: int | None = None,
    min_rank: int | None = None,
    max_rank: int | None = None,
) -> list[RankedWord]:
    """Load ``rank<TAB>word`` (or whitespace-separated) rows deterministically."""
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


def _ipa_units(value: str, *, keep_stress: bool, split_tie_bars: bool) -> tuple[str, ...]:
    value = unicodedata.normalize("NFC", value).strip()
    units: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        index += 1
        if char.isspace():
            units.append(char)
            continue
        if char in STRESS_MARKS and not keep_stress:
            continue
        if unicodedata.combining(char):
            if units:
                units[-1] += char
            continue

        unit = char
        while (
            index < len(value)
            and unicodedata.combining(value[index])
            and value[index] not in TIE_BARS
        ):
            unit += value[index]
            index += 1
        if not split_tie_bars and index < len(value) and value[index] in TIE_BARS:
            unit += value[index]
            index += 1
            if index < len(value):
                unit += value[index]
                index += 1
                while index < len(value) and unicodedata.combining(value[index]):
                    unit += value[index]
                    index += 1
        elif split_tie_bars and index < len(value) and value[index] in TIE_BARS:
            index += 1
        units.append(unit)
    return tuple(units)


def normalize_exact_ipa(value: str, *, ignore_stress: bool = False) -> tuple[str, ...]:
    """Normalize IPA for exact comparison while retaining meaningful detail."""
    return _ipa_units(value, keep_stress=not ignore_stress, split_tie_bars=False)


def normalize_broad_ipa(value: str, *, ignore_stress: bool = True) -> tuple[str, ...]:
    """Conservatively normalize notation/stress differences for broad comparison."""
    return tuple(
        unit
        for unit in _ipa_units(value, keep_stress=not ignore_stress, split_tie_bars=True)
        if not unit.isspace()
    )


def levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    """Return edit distance between two token sequences."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for index_a, item_a in enumerate(a, 1):
        current = [index_a]
        for index_b, item_b in enumerate(b, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index_b] + 1,
                    previous[index_b - 1] + (item_a != item_b),
                )
            )
        previous = current
    return previous[-1]


def pronunciation_distance(
    a: str,
    b: str,
    *,
    broad: bool,
    ignore_stress: bool | None = None,
) -> DistanceResult:
    tokenize = normalize_broad_ipa if broad else normalize_exact_ipa
    if ignore_stress is None:
        ignore_stress = broad
    first = tokenize(a, ignore_stress=ignore_stress)
    second = tokenize(b, ignore_stress=ignore_stress)
    edits = levenshtein(first, second)
    denominator = max(len(first), len(second))
    return DistanceResult(edits, edits / denominator if denominator else 0.0)


def classify_distance(value: float) -> str:
    if value == 0.0:
        return "match"
    if value <= 0.15:
        return "very_close"
    if value <= 0.30:
        return "different"
    if value <= 0.50:
        return "inspect"
    return "strong_disagreement"


def frequency_band(rank: int) -> str:
    for limit in BAND_LIMITS:
        if rank <= limit:
            return f"top_{limit}"
    return "beyond_top_50000"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ReferenceResult:
    status: str
    ipa: str | None = None
    source_pronunciation: str | None = None
    error: str | None = None


def _reference_result(raw: object, provider: PronunciationProvider) -> ReferenceResult:
    if raw is None:
        return ReferenceResult("unavailable")
    if not isinstance(raw, str) or not raw.strip():
        return ReferenceResult("error", error="reference returned malformed pronunciation")
    try:
        normalized = normalize_pronunciation(
            raw, str(getattr(provider, "source_encoding", "ipa"))
        ).pronunciation
    except Exception as error:  # noqa: BLE001
        return ReferenceResult("error", error=str(error))
    return ReferenceResult("ok", normalized, raw.strip())


def _call_reference(provider: PronunciationProvider, word: str, language: str) -> ReferenceResult:
    try:
        raw = provider.phonemize(word, language)
    except Exception as error:  # noqa: BLE001
        return ReferenceResult("error", error=str(error))
    return _reference_result(raw, provider)


def generate_references(
    words: Sequence[str],
    *,
    language: str,
    provider: PronunciationProvider,
) -> dict[str, ReferenceResult]:
    """Generate independent references, using batching without losing per-word errors."""
    values = tuple(words)
    if not values:
        return {}
    if isinstance(provider, BatchPronunciationProvider):
        try:
            raw_values = tuple(provider.phonemize_many(values, language))
            if len(raw_values) != len(values):
                raise ProviderOutputError(
                    f"reference returned {len(raw_values)} results for {len(values)} words"
                )
            return {word: _reference_result(raw, provider) for word, raw in zip(values, raw_values)}
        except Exception:  # noqa: BLE001
            # A batch failure must not discard useful per-word evidence.
            return {word: _call_reference(provider, word, language) for word in values}
    return {word: _call_reference(provider, word, language) for word in values}


def _empty_row(item: RankedWord) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "word": item.word,
        "found": False,
        "matched_key": None,
        "lexicon_variants": [],
        "lexicon_source_pronunciations": [],
        "reference": "espeak",
        "reference_status": "not_run",
        "reference_version": None,
        "reference_language": None,
        "reference_ipa": None,
        "reference_source_pronunciation": None,
        "reference_error": None,
        "best_variant_index": None,
        "exact_distance": None,
        "broad_distance": None,
        "classification": None,
    }


def collect_validation_rows(
    words: Sequence[RankedWord],
    *,
    language: str,
    engine: Phonemizer,
    provider: PronunciationProvider,
    ignore_stress: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    found_rows: list[dict[str, Any]] = []
    for item in words:
        row = _empty_row(item)
        try:
            token = engine.lookup_lexicon(item.word)
        except Exception as error:  # noqa: BLE001
            row["reference_status"] = "not_run"
            row["lexicon_error"] = str(error)
            rows.append(row)
            continue
        if token is not None and getattr(token, "variants", ()):
            row["found"] = True
            row["matched_key"] = getattr(token, "matched_key", None)
            variants = tuple(getattr(variant, "pronunciation", "") for variant in token.variants)
            source_variants = tuple(
                getattr(variant, "source_pronunciation", "") for variant in token.variants
            )
            row["lexicon_variants"] = list(variants)
            row["lexicon_source_pronunciations"] = list(source_variants)
            found_rows.append(row)
        rows.append(row)

    references = generate_references(
        [row["word"] for row in found_rows], language=language, provider=provider
    )
    for row in found_rows:
        reference = references[row["word"]]
        row["reference_status"] = reference.status
        row["reference_language"] = language
        row["reference_ipa"] = reference.ipa
        row["reference_source_pronunciation"] = reference.source_pronunciation
        row["reference_error"] = reference.error
        if reference.status != "ok" or not row["lexicon_variants"]:
            continue
        exact = [
            pronunciation_distance(
                variant, reference.ipa or "", broad=False, ignore_stress=ignore_stress
            )
            for variant in row["lexicon_variants"]
        ]
        broad = [
            pronunciation_distance(
                variant, reference.ipa or "", broad=True, ignore_stress=ignore_stress
            )
            for variant in row["lexicon_variants"]
        ]
        best_index = min(
            range(len(broad)),
            key=lambda index: (broad[index].normalized, exact[index].normalized, index),
        )
        row["best_variant_index"] = best_index
        row["exact_distance"] = min(result.normalized for result in exact)
        row["broad_distance"] = broad[best_index].normalized
        row["classification"] = classify_distance(broad[best_index].normalized)
    return rows


def _percentage(found: int, total: int) -> float:
    return round(found * 100 / total, 2) if total else 0.0


def _band_rows(rows: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [row for row in rows if row["rank"] <= limit]


def _comparison_counts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in rows if row["broad_distance"] is not None]
    values = [float(row["broad_distance"]) for row in comparable]
    counts = {
        "compared": len(comparable),
        "exact_matches": sum(row["exact_distance"] == 0 for row in comparable),
        "broad_matches": sum(row["broad_distance"] == 0 for row in comparable),
        "very_close": sum(row["classification"] == "very_close" for row in comparable),
        "different": sum(row["classification"] == "different" for row in comparable),
        "inspect": sum(row["classification"] == "inspect" for row in comparable),
        "strong_disagreement": sum(
            row["classification"] == "strong_disagreement" for row in comparable
        ),
        "mean_broad_distance": round(statistics.mean(values), 6) if values else None,
        "median_broad_distance": round(statistics.median(values), 6) if values else None,
    }
    return counts


def build_summary(
    rows: Sequence[dict[str, Any]],
    *,
    language: str,
    lexicon: str,
    reference_version: str | None,
    word_list_source: str,
    word_list_limit: int | None,
    word_list_sha256: str | None,
    word_list_retrieved_date: str | None = None,
    lexicon_metadata: dict[str, Any] | None = None,
    ignore_stress: bool = False,
    report_threshold: float = 0.30,
    max_distance: float = 1.0,
) -> dict[str, Any]:
    tested = len(rows)
    found = sum(bool(row["found"]) for row in rows)
    coverage_bands: dict[str, Any] = {}
    comparison_bands: dict[str, Any] = {}
    for limit in BAND_LIMITS:
        band = _band_rows(rows, limit)
        band_found = sum(bool(row["found"]) for row in band)
        band_comparison = [row for row in band if row["broad_distance"] is not None]
        coverage_bands[f"top_{limit}"] = {
            "requested": len(band),
            "found": band_found,
            "missing": len(band) - band_found,
            "coverage_percentage": _percentage(band_found, len(band)),
        }
        comparison_bands[f"top_{limit}"] = _comparison_counts(band_comparison)
    metadata = lexicon_metadata or {}
    return {
        "schema_version": 1,
        "language": language,
        "lexicon": lexicon,
        "reference": {"name": "espeak", "version": reference_version},
        "word_list": {
            "source": word_list_source,
            "limit": word_list_limit,
            "sha256": word_list_sha256,
            "retrieved_date": word_list_retrieved_date,
        },
        "coverage": {
            "total_words_requested": tested,
            "total_words_processed": tested,
            "tested": tested,
            "found": found,
            "missing": tested - found,
            "coverage_percentage": _percentage(found, tested),
            "bands": coverage_bands,
        },
        "comparison": {**_comparison_counts(rows), "bands": comparison_bands},
        "reporting": {
            "report_threshold": report_threshold,
            "max_distance": max_distance,
            "ignore_stress": ignore_stress,
        },
        "provenance": {
            "lexphon_version": _lexphon_version(),
            "lexicon_id": lexicon,
            "lexicon_data_version": metadata.get("data_version"),
            "lexicon_logical_sha256": metadata.get("logical_sha256"),
            "reference_provider": "espeak",
            "reference_version": reference_version,
            "script_schema_version": 1,
            "comparison_settings": {
                "ignore_stress": ignore_stress,
                "report_threshold": report_threshold,
                "max_distance": max_distance,
            },
        },
    }


def _lexphon_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("lexphon")
    except Exception:  # noqa: BLE001
        return None


def reference_version(provider: PronunciationProvider) -> str | None:
    executable = getattr(provider, "executable", None)
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0] if output else None


def _reported_rows(
    rows: Iterable[dict[str, Any]], *, report_threshold: float, max_distance: float
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row["broad_distance"] is not None
        and report_threshold < row["broad_distance"] <= max_distance
    ]
    return sorted(
        selected,
        key=lambda row: (
            -SEVERITY.get(row["classification"], -1),
            -row["broad_distance"],
            row["rank"],
            row["word"],
        ),
    )


CSV_FIELDS = (
    "rank",
    "word",
    "found",
    "matched_key",
    "lexicon_ipa",
    "lexicon_variants",
    "best_variant_index",
    "reference_ipa",
    "exact_distance",
    "broad_distance",
    "classification",
    "reference",
    "reference_version",
    "reference_status",
    "reference_error",
)


def write_mismatches(
    path: Path,
    rows: Iterable[dict[str, Any]],
    *,
    report_threshold: float = 0.30,
    max_distance: float = 1.0,
    reference_version: str | None = None,
) -> list[dict[str, Any]]:
    reported = _reported_rows(rows, report_threshold=report_threshold, max_distance=max_distance)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in reported:
            variants = row["lexicon_variants"]
            writer.writerow(
                {
                    "rank": row["rank"],
                    "word": row["word"],
                    "found": row["found"],
                    "matched_key": row["matched_key"] or "",
                    "lexicon_ipa": variants[row["best_variant_index"]] if variants else "",
                    "lexicon_variants": json.dumps(
                        variants, ensure_ascii=False, separators=(",", ":")
                    ),
                    "best_variant_index": row["best_variant_index"],
                    "reference_ipa": row["reference_ipa"] or "",
                    "exact_distance": row["exact_distance"],
                    "broad_distance": row["broad_distance"],
                    "classification": row["classification"],
                    "reference": "espeak",
                    "reference_version": reference_version or "",
                    "reference_status": row["reference_status"],
                    "reference_error": row["reference_error"] or "",
                }
            )
    return reported


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _download_word_list(url: str, target: Path) -> Path:
    """Download the configured source and adapt word-only lists to ranked TSV."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read().decode("utf-8-sig")
    except Exception as error:
        raise RuntimeError(f"unable to download word list from {url}: {error}") from error
    adapted: list[str] = []
    for rank, raw_line in enumerate(payload.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split("\t", 1) if "\t" in line else line.split(None, 1)
        if len(fields) == 2 and fields[0].strip().isdigit():
            adapted.append(f"{fields[0].strip()}\t{fields[1].strip()}")
        else:
            adapted.append(f"{rank}\t{line}")
    target.write_text("\n".join(adapted) + ("\n" if adapted else ""), encoding="utf-8")
    return target


def _word_list_path(args: argparse.Namespace) -> tuple[Path, str, str | None]:
    if args.word_list and args.download_word_list:
        raise ValueError("use either --word-list or --download-word-list, not both")
    if args.word_list:
        path = args.word_list
        return path, str(path), None
    if not args.download_word_list:
        raise ValueError("provide --word-list or explicitly request --download-word-list")
    url = args.word_list_url or DEFAULT_WORD_LIST_URL
    path = args.cache_dir / args.language / "words.tsv"
    if not path.is_file():
        _download_word_list(url, path)
    retrieved = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat()
    return path, url, retrieved


DEFAULT_WORD_LIST_URL = "https://raw.githubusercontent.com/oprogramador/most-common-words-by-language/master/src/resources/german.txt"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="de-DE")
    parser.add_argument("--lexicon", default="de-de:gold")
    parser.add_argument("--reference", choices=("espeak",), default="espeak")
    parser.add_argument("--word-list", type=Path)
    parser.add_argument("--download-word-list", action="store_true")
    parser.add_argument("--word-list-url")
    parser.add_argument("--cache-dir", type=Path, default=Path(".validation-cache"))
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--min-rank", type=int)
    parser.add_argument("--max-rank", type=int)
    parser.add_argument("--max-distance", type=float, default=1.0)
    parser.add_argument("--report-threshold", type=float, default=0.30)
    parser.add_argument("--ignore-stress", action="store_true")
    return parser


def _console_summary(summary: dict[str, Any], *, summary_path: Path, mismatches_path: Path) -> str:
    coverage = summary["coverage"]
    comparison = summary["comparison"]
    return "\n".join(
        (
            "Lexphon pronunciation validation",
            "--------------------------------",
            f"language:            {summary['language']}",
            f"lexicon:             {summary['lexicon']}",
            f"reference:           {summary['reference']['name']}",
            f"words checked:       {coverage['tested']:,}",
            "",
            "coverage",
            f"  found:             {coverage['found']:,}  {coverage['coverage_percentage']:.2f}%",
            f"  missing:           {coverage['missing']:,}  {_percentage(coverage['missing'], coverage['tested']):.2f}%",
            "",
            "pronunciation comparison",
            f"  compared:          {comparison['compared']:,}",
            f"  exact match:       {comparison['exact_matches']:,}",
            f"  broad match:       {comparison['broad_matches']:,}",
            f"  inspect > 0.30:    {comparison['inspect'] + comparison['strong_disagreement']:,}",
            f"  strong > 0.50:     {comparison['strong_disagreement']:,}",
            "",
            "output",
            f"  {summary_path}",
            f"  {mismatches_path}",
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.report_threshold < 0 or args.max_distance < 0:
        parser.error("distance thresholds must be non-negative")
    try:
        word_path, word_source, retrieved_date = _word_list_path(args)
        words = load_ranked_words(
            word_path, limit=args.limit, min_rank=args.min_rank, max_rank=args.max_rank
        )
        store = DataStore(args.data_home)
        lexicon_metadata = store.metadata(args.lexicon)
        provider = EspeakProvider() if args.reference == "espeak" else None
        if provider is None:
            raise ValueError(f"unsupported reference {args.reference!r}")
        engine = Phonemizer(args.language, lexicons=[args.lexicon], store=store, fallback=None)
        try:
            rows = collect_validation_rows(
                words,
                language=args.language,
                engine=engine,
                provider=provider,
                ignore_stress=args.ignore_stress,
            )
        finally:
            engine.close()
        version = reference_version(provider)
        output_dir = args.output_dir or Path("validation") / args.language
        summary_path = output_dir / "summary.json"
        mismatches_path = output_dir / "mismatches.csv"
        summary = build_summary(
            rows,
            language=args.language,
            lexicon=args.lexicon,
            reference_version=version,
            word_list_source=word_source,
            word_list_limit=args.limit,
            word_list_sha256=_sha256(word_path),
            word_list_retrieved_date=retrieved_date,
            lexicon_metadata=lexicon_metadata,
            ignore_stress=args.ignore_stress,
            report_threshold=args.report_threshold,
            max_distance=args.max_distance,
        )
        write_summary(summary_path, summary)
        write_mismatches(
            mismatches_path,
            rows,
            report_threshold=args.report_threshold,
            max_distance=args.max_distance,
            reference_version=version,
        )
        print(_console_summary(summary, summary_path=summary_path, mismatches_path=mismatches_path))
        return 0
    except LexiconNotInstalledError:
        print(
            f"{args.lexicon} is not installed\nrun:\n  lexphon data install {args.lexicon}",
            file=sys.stderr,
        )
        return 2
    except ProviderUnavailableError:
        print(
            "eSpeak reference provider is unavailable.\n"
            "Install eSpeak/eSpeak-ng or choose another reference.",
            file=sys.stderr,
        )
        return 2
    except (OSError, ProviderError, ValueError, RuntimeError) as error:
        print(f"validation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
