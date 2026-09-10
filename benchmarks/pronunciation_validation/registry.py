"""Discovery and consistency checks for checked-in lexicon benchmark specs."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

from lexphon.catalog import Catalog

from .catalog import is_quality_benchmark_artifact, iter_quality_benchmark_artifacts
from .model import BenchmarkSpec

EXPECTED_PRODUCTION_IDS = (
    "ar:lexhint", "az:lexhint", "bg:lexhint", "ca:lexhint", "ceb:lexhint", "cs:lexhint",
    "cs:lexhint-native", "de-de:crane", "de-de:espeak", "de-de:gold", "de-de:lexhint",
    "de-de:lexhint-native", "de-de:olaph", "el:lexhint", "el:lexhint-native", "en-gb:gold",
    "en-gb:lexhint", "en-us:cmudict", "en-us:gold", "en-us:lexhint", "es:lexhint",
    "es:lexhint-native", "fr-fr:gold", "fr:lexhint", "fr:lexhint-native", "ga:lexhint",
    "he:lexhint", "hi:lexhint", "hu:lexhint", "hy:lexhint", "id:lexhint-native", "it:lexhint",
    "it:lexhint-native", "ja:lexhint", "ja:lexhint-native", "ko:lexhint", "ko:lexhint-native",
    "ku:lexhint-native", "la:lexhint", "lt:lexhint", "lv:lexhint", "mr:lexhint",
    "ms:lexhint-native", "nl:lexhint", "pl:lexhint", "pl:lexhint-native", "pt-br:lexhint",
    "pt-pt:lexhint", "pt:lexhint", "pt:lexhint-native", "ro:lexhint", "ru:lexhint",
    "ru:lexhint-native", "sv-se:nst", "sv:lexhint", "ta:lexhint", "te:lexhint",
    "th:lexhint-native", "tl:lexhint", "tr:lexhint", "tr:lexhint-native", "uk:lexhint",
    "ur:lexhint", "vi:lexhint", "vi:lexhint-native", "zh:lexhint", "zh:lexhint-native",
)


def filename_for_id(identifier: str) -> str:
    safe = identifier.replace("-", "_").replace(":", "_").replace(".", "_")
    return f"benchmark_{safe}.py"


def module_name_for_id(identifier: str) -> str:
    return f"benchmarks.pronunciation_validation.lexicons.{filename_for_id(identifier)[:-3]}"


def discover_modules() -> tuple[ModuleType, ...]:
    from . import lexicons

    modules = []
    for info in pkgutil.iter_modules(lexicons.__path__):
        if info.name.startswith("benchmark_"):
            modules.append(importlib.import_module(f"{lexicons.__name__}.{info.name}"))
    return tuple(sorted(modules, key=lambda module: module.__name__))


def discover_specs() -> tuple[BenchmarkSpec, ...]:
    specs = []
    for module in discover_modules():
        spec = getattr(module, "SPEC", None)
        if isinstance(spec, BenchmarkSpec):
            specs.append(spec)
    return tuple(specs)


def spec_map(specs: Iterable[BenchmarkSpec] | None = None) -> dict[str, BenchmarkSpec]:
    values = tuple(specs if specs is not None else discover_specs())
    return {spec.lexicon_id: spec for spec in values}


def validate_specs(catalog: Catalog | None = None, specs: Iterable[BenchmarkSpec] | None = None) -> list[str]:
    values = tuple(specs if specs is not None else discover_specs())
    issues: list[str] = []
    ids = [spec.lexicon_id for spec in values]
    if len(ids) != len(set(ids)):
        issues.append("duplicate logical IDs in benchmark specs")
    for module in discover_modules():
        spec = getattr(module, "SPEC", None)
        if not isinstance(spec, BenchmarkSpec):
            issues.append(f"{module.__name__} must define exactly one BenchmarkSpec named SPEC")
            continue
        expected_name = filename_for_id(spec.lexicon_id)[:-3]
        if module.__name__.rsplit(".", 1)[-1] != expected_name:
            issues.append(f"{module.__name__} does not match {expected_name}")
    if catalog is not None:
        expected = {artifact.id for artifact in iter_quality_benchmark_artifacts(catalog)}
        actual = set(ids)
        for identifier in sorted(expected - actual):
            issues.append(f"missing benchmark module for {identifier}")
        for identifier in sorted(actual - expected):
            issues.append(f"stale benchmark module for {identifier}")
        for artifact in catalog.artifacts:
            if not is_quality_benchmark_artifact(artifact) and artifact.id in actual:
                issues.append(f"fixture or non-pronunciation artifact has benchmark module: {artifact.id}")
    return issues


def expected_module_paths(root: Path | None = None) -> tuple[Path, ...]:
    directory = root or Path(__file__).resolve().parent / "lexicons"
    return tuple(directory / filename_for_id(identifier) for identifier in EXPECTED_PRODUCTION_IDS)
