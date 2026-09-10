"""Lexicon-only lookup and row-level pronunciation comparison."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lexphon.providers import PronunciationProvider

from .distance import classify_distance, normalize_broad_ipa, pronunciation_distance
from .model import RankedWord
from .references import generate_references


def _empty_row(item: RankedWord, provider: PronunciationProvider) -> dict[str, Any]:
    name = getattr(provider, "name", None)
    encoding = getattr(provider, "source_encoding", None)
    return {
        "rank": item.rank,
        "word": item.word,
        "found": False,
        "status": "missing",
        "matched_key": None,
        "lexicon_variants": [],
        "lexicon_source_pronunciations": [],
        "reference": name,
        "reference_status": "not_run",
        "reference_version": None,
        "reference_language": None,
        "reference_source_encoding": encoding,
        "reference_ipa": None,
        "reference_source_pronunciation": None,
        "reference_error": None,
        "best_variant_index": None,
        "minimum_exact_distance": None,
        "exact_distance": None,
        "broad_distance": None,
        "exact_edits": None,
        "broad_edits": None,
        "broad_denominator": None,
        "classification": None,
    }


def collect_validation_rows(
    words: Sequence[RankedWord],
    *,
    language: str,
    engine: Any,
    provider: PronunciationProvider,
    ignore_stress: bool = False,
    strong_threshold: float = 0.50,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    found_rows: list[dict[str, Any]] = []
    for item in words:
        row = _empty_row(item, provider)
        try:
            token = engine.lookup_lexicon(item.word)
        except Exception as error:  # noqa: BLE001
            row["status"] = "lookup_error"
            row["reference_status"] = "not_run"
            row["lexicon_error"] = str(error)
            rows.append(row)
            continue
        if token is not None and getattr(token, "variants", ()):
            row["found"] = True
            row["status"] = "found"
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
        row["reference"] = reference.provider or getattr(provider, "name", None)
        row["reference_version"] = reference.version
        row["reference_language"] = language
        row["reference_source_encoding"] = reference.source_encoding
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
            range(len(broad)), key=lambda index: (broad[index].normalized, exact[index].normalized, index)
        )
        row["best_variant_index"] = best_index
        row["minimum_exact_distance"] = min(result.normalized for result in exact)
        row["exact_distance"] = exact[best_index].normalized
        row["broad_distance"] = broad[best_index].normalized
        row["exact_edits"] = exact[best_index].edits
        row["broad_edits"] = broad[best_index].edits
        row["broad_denominator"] = max(
            len(normalize_broad_ipa(row["lexicon_variants"][best_index], ignore_stress=ignore_stress)),
            len(normalize_broad_ipa(reference.ipa or "", ignore_stress=ignore_stress)),
        )
        row["classification"] = classify_distance(
            broad[best_index].normalized, strong_threshold=strong_threshold
        )
    return rows
