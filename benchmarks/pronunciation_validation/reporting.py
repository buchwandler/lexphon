"""Deterministic benchmark summaries and failure/report row writers."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .distance import BAND_LIMITS, SEVERITY
from .distance import comparison_metrics as legacy_comparison_metrics
from .phonetic import phonetic_comparison_metrics

SCHEMA_VERSION = 3
CSV_FIELDS = (
    "rank",
    "word",
    "status",
    "found",
    "matched_key",
    "lexicon_ipa",
    "lexicon_variants",
    "best_variant_index",
    "reference_ipa",
    "exact_distance",
    "minimum_exact_distance",
    "broad_distance",
    "classification",
    "phonetic_status",
    "phonetic_lexicon_ipa",
    "phonetic_best_variant_index",
    "phonetic_distance",
    "phonetic_raw_cost",
    "phonetic_denominator",
    "phonetic_selector_disagrees",
    "phonetic_error",
    "phonetic_operations",
    "reference",
    "reference_version",
    "reference_language",
    "reference_status",
    "reference_error",
    "lexicon_error",
)


def _percentage(value: int, total: int) -> float:
    return round(value * 100 / total, 2) if total else 0.0


def _comparison_counts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return legacy_comparison_metrics(rows)


def _band_rows(rows: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [row for row in rows if row["rank"] <= limit]


def build_summary(
    rows: Sequence[dict[str, Any]],
    *,
    language: str,
    lexicon: str,
    reference_version: str | None = None,
    word_list_source: str | None = None,
    word_list_limit: int | None = None,
    word_list_sha256: str | None = None,
    word_list_retrieved_date: str | None = None,
    lexicon_metadata: dict[str, Any] | None = None,
    ignore_stress: bool = False,
    report_threshold: float = 0.30,
    strong_threshold: float = 0.50,
    report_max_distance: float = 1.0,
    provider_name: str | None = None,
    provider_encoding: str | None = None,
    reference_relationship: str = "unknown",
    catalog_metadata: dict[str, Any] | None = None,
    word_list_metadata: dict[str, Any] | None = None,
    phonetic_metadata: dict[str, Any] | None = None,
    module: str | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    tested = len(rows)
    found = sum(bool(row.get("found")) for row in rows)
    coverage_bands: dict[str, Any] = {}
    comparison_bands: dict[str, Any] = {}
    for limit in BAND_LIMITS:
        band = _band_rows(rows, limit)
        band_found = sum(bool(row.get("found")) for row in band)
        coverage_bands[f"top_{limit}"] = {
            "requested": len(band),
            "found": band_found,
            "missing": len(band) - band_found,
            "coverage_percentage": _percentage(band_found, len(band)),
        }
        comparison_bands[f"top_{limit}"] = {
            **_comparison_counts([row for row in band if row.get("broad_distance") is not None]),
            "phonetic": phonetic_comparison_metrics(band),
        }
    metadata = lexicon_metadata or {}
    provider_name = provider_name or next(
        (row.get("reference") for row in rows if row.get("reference")), None
    )
    word_data = word_list_metadata or {}
    catalog_data = catalog_metadata or {}
    reference_data = {
        "name": provider_name,
        "version": reference_version,
        "language": language,
        "source_encoding": provider_encoding,
        "relationship": reference_relationship,
    }
    phonetic_data = phonetic_metadata or {
        "status": "not_run",
        "requested_language": language,
    }
    comparison = {
        **_comparison_counts(rows),
        "phonetic": phonetic_comparison_metrics(list(rows)),
        "bands": comparison_bands,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "benchmark": {"lexicon_id": lexicon, "language": language, "module": module},
        "phonetic": phonetic_data,
        "catalog": {
            "source": catalog_data.get("source"),
            "data_version": catalog_data.get("data_version", metadata.get("data_version")),
            "release_tag": catalog_data.get("release_tag"),
        },
        "lexicon": {
            "id": lexicon,
            "kind": metadata.get("kind", "pronunciation"),
            "phoneme_encoding": metadata.get("phoneme_encoding"),
            "logical_sha256": metadata.get("logical_sha256"),
            "asset_sha256": metadata.get("asset_sha256"),
        },
        "word_list": {
            "source_id": word_data.get("source_id", word_list_source),
            "source": word_list_source,
            "url": word_data.get("url"),
            "revision": word_data.get("revision"),
            "format": word_data.get("format"),
            "license_note": word_data.get("license_note"),
            "download_sha256": word_data.get("download_sha256", word_list_sha256),
            "ranked_sha256": word_data.get("ranked_sha256"),
            "retrieved_at": word_data.get("retrieved_at", word_list_retrieved_date),
            "requested_limit": word_list_limit,
            "rejected_rows": word_data.get("rejected_rows", 0),
            "rejected_phrases": word_data.get("rejected_phrases", 0),
        },
        "reference": reference_data,
        "coverage": {
            "total_words_requested": tested,
            "total_words_processed": tested,
            "tested": tested,
            "found": found,
            "missing": tested - found,
            "lookup_errors": sum(row.get("status") == "lookup_error" for row in rows),
            "reference_unavailable": sum(
                row.get("reference_status") == "unavailable" for row in rows
            ),
            "reference_errors": sum(row.get("reference_status") == "error" for row in rows),
            "coverage_percentage": _percentage(found, tested),
            "bands": coverage_bands,
        },
        "comparison": comparison,
        "reporting": {
            "report_threshold": report_threshold,
            "report_max_distance": report_max_distance,
            "ignore_stress": ignore_stress,
            "strong_threshold": strong_threshold,
        },
        "provenance": {
            "lexphon_version": _lexphon_version(),
            "lexicon_id": lexicon,
            "lexicon_data_version": metadata.get("data_version"),
            "lexicon_logical_sha256": metadata.get("logical_sha256"),
            "reference_provider": provider_name,
            "reference_version": reference_version,
            "script_schema_version": SCHEMA_VERSION,
            "comparison_settings": {
                "ignore_stress": ignore_stress,
                "report_threshold": report_threshold,
                "strong_threshold": strong_threshold,
            },
        },
    }


def _lexphon_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("lexphon")
    except Exception:  # noqa: BLE001
        return None


def _reported_rows(
    rows: Iterable[dict[str, Any]], *, report_threshold: float
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row.get("broad_distance") is not None and row["broad_distance"] > report_threshold
    ]
    return sorted(
        selected,
        key=lambda row: (
            -SEVERITY.get(row.get("classification") or "", -1),
            -float(row["broad_distance"]),
            row["rank"],
            row["word"],
        ),
    )


def _csv_row(row: dict[str, Any]) -> dict[str, Any]:
    variants = row.get("lexicon_variants", [])
    index = row.get("best_variant_index")
    phonetic_index = row.get("phonetic_best_variant_index")
    operations = row.get("phonetic_operations")
    return {
        "rank": row.get("rank"),
        "word": row.get("word"),
        "status": row.get("status"),
        "found": row.get("found"),
        "matched_key": row.get("matched_key") or "",
        "lexicon_ipa": variants[index] if variants and index is not None else "",
        "lexicon_variants": json.dumps(variants, ensure_ascii=False, separators=(",", ":")),
        "best_variant_index": index,
        "reference_ipa": row.get("reference_ipa") or "",
        "exact_distance": row.get("exact_distance"),
        "minimum_exact_distance": row.get("minimum_exact_distance"),
        "broad_distance": row.get("broad_distance"),
        "classification": row.get("classification"),
        "phonetic_status": row.get("phonetic_status"),
        "phonetic_lexicon_ipa": (
            variants[phonetic_index] if variants and phonetic_index is not None else ""
        ),
        "phonetic_best_variant_index": phonetic_index,
        "phonetic_distance": row.get("phonetic_distance"),
        "phonetic_raw_cost": row.get("phonetic_raw_cost"),
        "phonetic_denominator": row.get("phonetic_denominator"),
        "phonetic_selector_disagrees": row.get("phonetic_selector_disagrees"),
        "phonetic_error": row.get("phonetic_error") or "",
        "phonetic_operations": json.dumps(operations, ensure_ascii=False, separators=(",", ":"))
        if operations is not None
        else "",
        "reference": row.get("reference") or "",
        "reference_version": row.get("reference_version") or "",
        "reference_language": row.get("reference_language") or "",
        "reference_status": row.get("reference_status"),
        "reference_error": row.get("reference_error") or "",
        "lexicon_error": row.get("lexicon_error") or "",
    }


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))


def write_mismatches(
    path: Path, rows: Iterable[dict[str, Any]], *, report_threshold: float = 0.30
) -> list[dict[str, Any]]:
    reported = _reported_rows(rows, report_threshold=report_threshold)
    write_csv(path, reported)
    return reported


def write_reports(
    output_dir: Path, rows: Sequence[dict[str, Any]], summary: dict[str, Any]
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "summary.json",
        "mismatches": output_dir / "mismatches.csv",
        "missing": output_dir / "missing.csv",
        "reference_errors": output_dir / "reference_errors.csv",
        "rows": output_dir / "rows.jsonl",
        "selector_disagreements": output_dir / "selector_disagreements.csv",
    }
    write_summary(paths["summary"], summary)
    write_mismatches(
        paths["mismatches"], rows, report_threshold=summary["reporting"]["report_threshold"]
    )
    write_csv(
        paths["selector_disagreements"],
        sorted(
            (row for row in rows if row.get("phonetic_selector_disagrees") is True),
            key=lambda row: (row.get("rank", 0), row.get("word", "")),
        ),
    )
    write_csv(paths["missing"], [row for row in rows if not row.get("found")])
    write_csv(
        paths["reference_errors"],
        [row for row in rows if row.get("reference_status") in {"error", "unavailable"}],
    )
    with paths["rows"].open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            )
    return paths


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
