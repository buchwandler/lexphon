"""Pure IPA tokenization and pronunciation distance functions."""

from __future__ import annotations

import statistics
import unicodedata
from collections.abc import Sequence
from typing import Any

from .model import DistanceResult

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
    return _ipa_units(value, keep_stress=not ignore_stress, split_tie_bars=False)


def normalize_broad_ipa(value: str, *, ignore_stress: bool = True) -> tuple[str, ...]:
    return tuple(
        unit
        for unit in _ipa_units(value, keep_stress=not ignore_stress, split_tie_bars=True)
        if not unit.isspace()
    )


def levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
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


def classify_distance(value: float, *, strong_threshold: float = 0.50) -> str:
    if value == 0.0:
        return "match"
    if value <= 0.15:
        return "very_close"
    if value <= 0.30:
        return "different"
    if value <= strong_threshold:
        return "inspect"
    return "strong_disagreement"


def frequency_band(rank: int) -> str:
    for limit in BAND_LIMITS:
        if rank <= limit:
            return f"top_{limit}"
    return "beyond_top_50000"


def comparison_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    comparable = [row for row in rows if row.get("broad_distance") is not None]
    values = [float(row["broad_distance"]) for row in comparable]
    broad_edits = sum(int(row.get("broad_edits") or 0) for row in comparable)
    denominator = sum(int(row.get("broad_denominator") or 0) for row in comparable)

    def percentile(percent: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * percent
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 6)

    return {
        "compared": len(comparable),
        "exact_matches": sum(row.get("exact_distance") == 0 for row in comparable),
        "broad_matches": sum(row.get("broad_distance") == 0 for row in comparable),
        "exact_match_rate": round(
            sum(row.get("exact_distance") == 0 for row in comparable) / len(comparable), 6
        )
        if comparable
        else 0.0,
        "broad_match_rate": round(
            sum(row.get("broad_distance") == 0 for row in comparable) / len(comparable), 6
        )
        if comparable
        else 0.0,
        "very_close": sum(row.get("classification") == "very_close" for row in comparable),
        "different": sum(row.get("classification") == "different" for row in comparable),
        "inspect": sum(row.get("classification") == "inspect" for row in comparable),
        "strong_disagreement": sum(
            row.get("classification") == "strong_disagreement" for row in comparable
        ),
        "strong_disagreement_rate": round(
            sum(row.get("classification") == "strong_disagreement" for row in comparable)
            / len(comparable),
            6,
        )
        if comparable
        else 0.0,
        "mean_broad_distance": round(statistics.mean(values), 6) if values else None,
        "median_broad_distance": round(statistics.median(values), 6) if values else None,
        "p90_broad_distance": percentile(0.90),
        "p95_broad_distance": percentile(0.95),
        "p99_broad_distance": percentile(0.99),
        "total_broad_edits": broad_edits,
        "total_broad_units": denominator,
        "micro_edit_rate": round(broad_edits / denominator, 6) if denominator else 0.0,
    }
