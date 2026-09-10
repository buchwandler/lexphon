"""Synchronize checked-in benchmark entrypoints with a producer catalog."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from .catalog import iter_quality_benchmark_artifacts, load_benchmark_catalog
from .registry import discover_specs, filename_for_id


def _module_text(identifier: str) -> str:
    return (
        "from benchmarks.pronunciation_validation.model import BenchmarkSpec\n"
        "from benchmarks.pronunciation_validation.runner import main_for\n\n"
        f"SPEC = BenchmarkSpec(lexicon_id={identifier!r})\n\n"
        "if __name__ == \"__main__\":\n"
        "    raise SystemExit(main_for(SPEC))\n"
    )


def catalog_drift(catalog_location: str | None = None) -> tuple[list[str], list[str]]:
    catalog = load_benchmark_catalog(catalog_location)
    expected = {artifact.id for artifact in iter_quality_benchmark_artifacts(catalog)}
    actual = {spec.lexicon_id for spec in discover_specs()}
    return sorted(expected - actual), sorted(actual - expected)


def synchronize(
    *,
    catalog_location: str | None = None,
    write: bool = False,
    directory: Path | None = None,
) -> tuple[list[Path], list[str], list[str]]:
    catalog = load_benchmark_catalog(catalog_location)
    expected = {artifact.id for artifact in iter_quality_benchmark_artifacts(catalog)}
    actual = {spec.lexicon_id for spec in discover_specs()}
    missing = sorted(expected - actual)
    stale = sorted(actual - expected)
    created: list[Path] = []
    if write:
        target_dir = directory or Path(__file__).resolve().parent / "lexicons"
        target_dir.mkdir(parents=True, exist_ok=True)
        for identifier in missing:
            path = target_dir / filename_for_id(identifier)
            if not path.exists():
                path.write_text(_module_text(identifier), encoding="utf-8")
                created.append(path)
    return created, missing, stale


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--catalog")
    args = parser.parse_args(argv)
    created, missing, stale = synchronize(catalog_location=args.catalog, write=args.write)
    for path in created:
        print(f"created {path}")
    if missing:
        print("missing benchmark modules:")
        for identifier in missing:
            print(f"  {identifier}")
    if stale:
        print("stale benchmark modules:")
        for identifier in stale:
            print(f"  {identifier}")
    if not missing and not stale:
        print("catalog and benchmark modules are synchronized")
    return 0 if not missing and not stale else 1


if __name__ == "__main__":
    raise SystemExit(main())
