"""Benchmark-local adapter for optional Phonodist pronunciation comparisons."""

from __future__ import annotations

import importlib
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .model import PhoneticProvenance, PhoneticVariantResult


@dataclass(frozen=True, slots=True)
class PhoneticContext:
    """Reusable Phonodist setup and immutable scoring provenance."""

    status: str
    requested_language: str
    library: str | None = None
    library_version: str | None = None
    metric: str | None = None
    metric_version: str | None = None
    profile: str | None = None
    profile_version: str | None = None
    backend: str | None = None
    backend_version: str | None = None
    feature_set: str | None = None
    stress_policy: str | None = None
    error: str | None = None
    _module: Any = None

    @property
    def active(self) -> bool:
        return self.status == "active"

    def as_dict(self) -> dict[str, Any]:
        provenance = PhoneticProvenance(
            status=self.status,
            requested_language=self.requested_language,
            library=self.library,
            library_version=self.library_version,
            metric=self.metric,
            metric_version=self.metric_version,
            profile=self.profile,
            profile_version=self.profile_version,
            backend=self.backend,
            backend_version=self.backend_version,
            feature_set=self.feature_set,
            stress_policy=self.stress_policy,
            error=self.error,
        )
        return {
            "status": provenance.status,
            "requested_language": provenance.requested_language,
            "library": provenance.library,
            "library_version": provenance.library_version,
            "metric": provenance.metric,
            "metric_version": provenance.metric_version,
            "profile": provenance.profile,
            "profile_version": provenance.profile_version,
            "backend": provenance.backend,
            "backend_version": provenance.backend_version,
            "feature_set": provenance.feature_set,
            "stress_policy": provenance.stress_policy,
            "error": provenance.error,
        }


def _import_phonodist() -> ModuleType:
    return importlib.import_module("phonodist")


def _library_version(module: Any) -> str | None:
    value = getattr(module, "__version__", None)
    return str(value) if value is not None else None


def create_phonetic_context(
    language: str, *, phonodist_module: ModuleType | None = None
) -> PhoneticContext:
    """Initialize Phonodist once and capture its scoring environment."""

    if phonodist_module is None:
        try:
            phonodist_module = _import_phonodist()
        except ModuleNotFoundError as error:
            if error.name != "phonodist":
                raise
            return PhoneticContext(
                status="dependency_unavailable",
                requested_language=language,
                library="phonodist",
                error="install lexphon[validation] to enable Phonodist validation",
            )

    library_version = _library_version(phonodist_module)
    try:
        phonodist_module.get_profile(language)
    except phonodist_module.UnknownLanguageProfileError:
        return PhoneticContext(
            status="profile_unavailable",
            requested_language=language,
            library="phonodist",
            library_version=library_version,
        )

    probe = phonodist_module.pronunciation_distance("", "", language=language, explain=False)
    return PhoneticContext(
        status="active",
        requested_language=language,
        library="phonodist",
        library_version=library_version,
        metric=probe.metric,
        metric_version=probe.metric_version,
        profile=probe.language,
        profile_version=probe.profile_version,
        backend=probe.backend,
        backend_version=probe.backend_version,
        feature_set=probe.feature_set,
        stress_policy="ignored_by_metric",
        _module=phonodist_module,
    )


def _unsupported_result(index: int, error: Exception) -> PhoneticVariantResult:
    return PhoneticVariantResult(index=index, status="unsupported_ipa", error=str(error))


def compare_variants(
    variants: tuple[str, ...],
    reference_ipa: str,
    *,
    context: PhoneticContext,
) -> tuple[dict[str, Any], ...]:
    """Compare every variant and return JSON-ready result mappings."""

    if not context.active:
        return tuple(
            PhoneticVariantResult(
                index=index,
                status=context.status,
                error=context.error,
            ).as_dict()
            for index in range(len(variants))
        )

    module = context._module
    results: list[dict[str, Any]] = []
    for index, variant in enumerate(variants):
        try:
            result = module.pronunciation_distance(
                variant,
                reference_ipa,
                language=context.requested_language,
                explain=False,
            )
        except (module.InvalidIPAError, module.UnknownSegmentError) as error:
            results.append(_unsupported_result(index, error).as_dict())
            continue
        results.append(
            PhoneticVariantResult(
                index=index,
                status="ok",
                distance=float(result.distance),
                raw_cost=float(result.raw_cost),
                denominator=float(result.denominator),
            ).as_dict()
        )
    return tuple(results)


def phonetic_comparison_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate independently scored Phonodist row evidence."""

    comparable = [row for row in rows if row.get("phonetic_distance") is not None]
    values = [float(row["phonetic_distance"]) for row in comparable]
    results = [result for row in rows for result in row.get("phonetic_variant_results", [])]
    successful_results = [result for result in results if result.get("status") == "ok"]

    def percentile(percent: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * percent
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 6)

    total_raw_cost = sum(float(result.get("raw_cost") or 0.0) for result in successful_results)
    total_units = sum(float(result.get("denominator") or 0.0) for result in successful_results)
    disagreements = sum(bool(row.get("phonetic_selector_disagrees")) for row in rows)
    unsupported = sum(result.get("status") == "unsupported_ipa" for result in results)
    compared = len(comparable)
    return {
        "compared": compared,
        "matches": sum(value == 0.0 for value in values),
        "match_rate": round(sum(value == 0.0 for value in values) / compared, 6)
        if compared
        else 0.0,
        "mean_distance": round(statistics.mean(values), 6) if values else None,
        "median_distance": round(statistics.median(values), 6) if values else None,
        "p90_distance": percentile(0.90),
        "p95_distance": percentile(0.95),
        "p99_distance": percentile(0.99),
        "total_raw_cost": round(total_raw_cost, 6),
        "total_units": round(total_units, 6),
        "micro_cost_rate": round(total_raw_cost / total_units, 6) if total_units else 0.0,
        "unsupported_ipa": unsupported,
        "selector_disagreements": disagreements,
        "selector_disagreement_rate": round(disagreements / compared, 6) if compared else 0.0,
    }


def _serialize_operations(result: Any) -> list[dict[str, Any]]:
    return [
        {
            "source": list(operation.source),
            "target": list(operation.target),
            "kind": operation.kind,
            "cost": operation.cost,
            "reason": operation.reason,
        }
        for operation in result.operations
    ]


def attach_phonetic_explanations(
    rows: list[dict[str, Any]],
    *,
    context: PhoneticContext,
    report_threshold: float,
) -> None:
    """Attach explanations only to legacy mismatches or selector disagreements."""

    if not context.active:
        return
    module = context._module
    for row in rows:
        interesting = (
            row.get("broad_distance") is not None and row["broad_distance"] > report_threshold
        ) or row.get("phonetic_selector_disagrees") is True
        index = row.get("phonetic_best_variant_index")
        reference = row.get("reference_ipa")
        variants = row.get("lexicon_variants", [])
        if not interesting or index is None or reference is None:
            continue
        try:
            result = module.pronunciation_distance(
                variants[index],
                reference,
                language=context.requested_language,
                explain=True,
            )
        except (module.InvalidIPAError, module.UnknownSegmentError):
            continue
        row["phonetic_operations"] = _serialize_operations(result)
