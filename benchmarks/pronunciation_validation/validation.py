"""Lexicon-only lookup and row-level pronunciation comparison."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lexphon.providers import PronunciationProvider

from .distance import classify_distance, normalize_broad_ipa, pronunciation_distance
from .model import ProviderSpec, RankedWord
from .progress import ProgressReporter
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
    provider_info: ProviderSpec | None = None,
    ignore_stress: bool = False,
    strong_threshold: float = 0.50,
    progress: ProgressReporter | None = None,
    progress_lexicon_id: str | None = None,
) -> list[dict[str, Any]]:
    label = progress_lexicon_id or str(getattr(provider, "name", "benchmark"))
    total = len(words)
    if progress is not None:
        progress.stage(label, "lookup", f"starting {total} words")
    rows: list[dict[str, Any]] = []
    found_rows: list[dict[str, Any]] = []
    lookup_errors = 0
    for current, item in enumerate(words, 1):
        row = _empty_row(item, provider)
        try:
            token = engine.lookup_lexicon(item.word)
        except Exception as error:  # noqa: BLE001
            lookup_errors += 1
            row["status"] = "lookup_error"
            row["reference_status"] = "not_run"
            row["lexicon_error"] = str(error)
            rows.append(row)
            if progress is not None:
                progress.counter(
                    label,
                    "lookup",
                    current,
                    total,
                    suffix=f"{len(found_rows)} found; {lookup_errors} lookup errors",
                )
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
        if progress is not None:
            progress.counter(
                label,
                "lookup",
                current,
                total,
                suffix=f"{len(found_rows)} found; {lookup_errors} lookup errors",
            )
    if progress is not None:
        progress.stage(
            label,
            "lookup",
            f"{total}/{total}; {len(found_rows)} found; {lookup_errors} lookup errors",
        )

    references = generate_references(
        [row["word"] for row in found_rows],
        language=language,
        provider=provider,
        provider_info=provider_info,
        progress=progress,
        progress_lexicon_id=label,
    )
    if progress is not None:
        progress.stage(label, "compare", f"starting {len(found_rows)} found rows")
    usable_references = 0
    reference_errors = 0
    for current, row in enumerate(found_rows, 1):
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
            reference_errors += 1
            if progress is not None:
                progress.counter(
                    label,
                    "compare",
                    current,
                    len(found_rows),
                    suffix=f"{usable_references} usable references",
                )
            continue
        usable_references += 1
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
        row["minimum_exact_distance"] = min(result.normalized for result in exact)
        row["exact_distance"] = exact[best_index].normalized
        row["broad_distance"] = broad[best_index].normalized
        row["exact_edits"] = exact[best_index].edits
        row["broad_edits"] = broad[best_index].edits
        row["broad_denominator"] = max(
            len(
                normalize_broad_ipa(
                    row["lexicon_variants"][best_index], ignore_stress=ignore_stress
                )
            ),
            len(normalize_broad_ipa(reference.ipa or "", ignore_stress=ignore_stress)),
        )
        row["classification"] = classify_distance(
            broad[best_index].normalized, strong_threshold=strong_threshold
        )
        if progress is not None:
            progress.counter(
                label,
                "compare",
                current,
                len(found_rows),
                suffix=f"{usable_references} usable references",
            )
    if progress is not None:
        progress.stage(
            label,
            "compare",
            f"{len(found_rows)}/{len(found_rows)}; {usable_references} usable references; {reference_errors} reference errors",
        )
    return rows
