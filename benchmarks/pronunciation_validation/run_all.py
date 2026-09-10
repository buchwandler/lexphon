"""Run the checked-in pronunciation benchmark matrix in one process."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .catalog import iter_quality_benchmark_artifacts, load_benchmark_catalog
from .model import BenchmarkPaths, BenchmarkSpec
from .progress import ProgressReporter
from .registry import discover_specs
from .runner import _safe_id, run_spec


def select_specs(
    specs: Sequence[BenchmarkSpec], *, language: str | None = None, lexicon: str | None = None
) -> tuple[BenchmarkSpec, ...]:
    if lexicon:
        return tuple(spec for spec in specs if spec.lexicon_id == lexicon)
    if language:
        key = language.casefold().replace("_", "-")
        return tuple(spec for spec in specs if spec.lexicon_id.split(":", 1)[0].casefold() == key)
    return tuple(specs)


def run_matrix(
    specs: Sequence[BenchmarkSpec],
    *,
    runner_args: Sequence[str] = (),
    output_root: Path | None = None,
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    reporter = progress or ProgressReporter()
    results = []
    total = len(specs)
    for index, spec in enumerate(specs, 1):
        reporter.benchmark(index, total, spec.lexicon_id)
        args = list(runner_args)
        if output_root is not None:
            args.extend(["--output-dir", str(output_root / _safe_id(spec.lexicon_id))])
        result = run_spec(spec, args, progress=reporter)
        comparison = result.summary.get("comparison", {})
        coverage = result.summary.get("coverage", {})
        phonetic = comparison.get("phonetic", {})
        phonetic_metadata = result.summary.get("phonetic", {})
        results.append(
            {
                "lexicon_id": spec.lexicon_id,
                "status": result.status,
                "coverage_percentage": coverage.get("coverage_percentage", 0.0),
                "compared": comparison.get("compared", 0),
                "mean_broad_distance": comparison.get("mean_broad_distance"),
                "phonetic_status": phonetic_metadata.get("status", "not_run"),
                "phonetic_compared": phonetic.get("compared", 0),
                "mean_phonetic_distance": phonetic.get("mean_distance"),
                "phonetic_selector_disagreement_rate": phonetic.get(
                    "selector_disagreement_rate", 0.0
                ),
                "phonetic_unsupported_ipa": phonetic.get("unsupported_ipa", 0),
                "strong_disagreement_rate": comparison.get("strong_disagreement_rate", 0.0),
            }
        )
    return {"schema_version": 2, "benchmarks": results}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog")
    parser.add_argument("--language")
    parser.add_argument("--lexicon")
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--word-list", type=Path)
    parser.add_argument("--refresh-word-list", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--min-rank", type=int)
    parser.add_argument("--max-rank", type=int)
    parser.add_argument("--reference", default="espeak")
    parser.add_argument("--reference-language")
    parser.add_argument("--report-threshold", type=float, default=0.30)
    parser.add_argument("--strong-threshold", type=float, default=0.50)
    parser.add_argument("--ignore-stress", action="store_true")
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument(
        "--require-phonodist",
        action="store_true",
        help="require Phonodist and language-specific profiles for selected benchmarks",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress benchmark progress output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    reporter = ProgressReporter(enabled=not args.quiet)
    specs = discover_specs()
    if args.catalog:
        catalog = load_benchmark_catalog(args.catalog)
        catalog_ids = {artifact.id for artifact in iter_quality_benchmark_artifacts(catalog)}
        specs = tuple(spec for spec in specs if spec.lexicon_id in catalog_ids)
    specs = select_specs(specs, language=args.language, lexicon=args.lexicon)
    if not specs:
        selector = (
            f"--lexicon {args.lexicon!r}" if args.lexicon else f"--language {args.language!r}"
        )
        print(f"no pronunciation benchmarks matched {selector}", file=sys.stderr, flush=True)
        return 2

    reporter.emit(
        f"pronunciation validation: {len(specs)} benchmarks selected; "
        f"limit={args.limit}; reference={args.reference}"
    )
    output_root = args.output_dir or BenchmarkPaths.default().reports
    runner_args: list[str] = []
    for flag, value in (
        ("--catalog", args.catalog),
        ("--data-home", args.data_home),
        ("--word-list", args.word_list),
        ("--limit", args.limit),
        ("--min-rank", args.min_rank),
        ("--max-rank", args.max_rank),
        ("--reference", args.reference),
        ("--reference-language", args.reference_language),
        ("--report-threshold", args.report_threshold),
        ("--strong-threshold", args.strong_threshold),
    ):
        if value is not None:
            runner_args.extend([flag, str(value)])
    for flag, enabled in (
        ("--refresh-word-list", args.refresh_word_list),
        ("--offline", args.offline),
        ("--ignore-stress", args.ignore_stress),
        ("--no-install", args.no_install),
        ("--require-phonodist", args.require_phonodist),
    ):
        if enabled:
            runner_args.append(flag)
    try:
        index = run_matrix(
            specs, runner_args=runner_args, output_root=output_root, progress=reporter
        )
    except KeyboardInterrupt:
        print("pronunciation validation interrupted by user", file=sys.stderr, flush=True)
        return 130
    index_path = output_root / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {index_path} ({len(specs)} benchmarks)")
    return 0 if all(item["status"] == "completed" for item in index["benchmarks"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
