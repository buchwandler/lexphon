"""Shared command-line runner for declarative pronunciation benchmarks."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from lexphon import DataStore, Phonemizer
from lexphon.errors import CatalogError, ProviderError, ProviderUnavailableError

from .catalog import CatalogResolution, load_benchmark_catalog, provision_artifact, resolve_artifact
from .model import BenchmarkPaths, BenchmarkRunResult, BenchmarkSpec, WordListResult
from .phonetic import attach_phonetic_explanations, create_phonetic_context
from .progress import ProgressReporter
from .references import create_reference, provider_spec
from .reporting import build_summary, write_reports
from .validation import collect_validation_rows
from .wordlists import ensure_word_list, load_ranked_words, resolve_word_list


def _safe_id(identifier: str) -> str:
    return identifier.replace(":", "__").replace("/", "_")


def _parser(spec: BenchmarkSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Run pronunciation benchmark for {spec.lexicon_id}"
    )
    parser.add_argument("--catalog")
    parser.add_argument("--data-home", type=Path)
    parser.add_argument("--word-list", type=Path)
    parser.add_argument("--word-list-url")
    parser.add_argument("--refresh-word-list", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--min-rank", type=int)
    parser.add_argument("--max-rank", type=int)
    parser.add_argument("--reference", default=spec.reference_name)
    parser.add_argument("--reference-language", default=spec.reference_language)
    parser.add_argument("--report-threshold", type=float, default=spec.report_threshold)
    parser.add_argument("--strong-threshold", type=float, default=spec.strong_threshold)
    parser.add_argument("--ignore-stress", action="store_true", default=spec.ignore_stress)
    parser.add_argument("--no-install", action="store_true")
    parser.add_argument(
        "--require-phonodist",
        action="store_true",
        help="require Phonodist and a language-specific profile for this benchmark",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress benchmark progress output.")
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.min_rank is not None and args.min_rank < 1:
        parser.error("--min-rank must be positive")
    if args.max_rank is not None and args.max_rank < 1:
        parser.error("--max-rank must be positive")
    if args.report_threshold < 0 or args.strong_threshold < 0:
        parser.error("distance thresholds must be non-negative")


def _word_list_result(
    args: argparse.Namespace, spec: BenchmarkSpec, language: str, paths: BenchmarkPaths
) -> WordListResult:
    source = resolve_word_list(spec.word_list_key, language)
    if args.word_list_url:
        source = replace(source, url=args.word_list_url)
    if args.word_list:
        words = tuple(
            load_ranked_words(
                args.word_list, limit=args.limit, min_rank=args.min_rank, max_rank=args.max_rank
            )
        )
        from .wordlists import _sha256

        return WordListResult(
            words=words,
            spec=source,
            source_path=args.word_list,
            download_sha256=_sha256(args.word_list),
            ranked_sha256=_sha256(args.word_list),
            retrieved_at=None,
        )
    result = ensure_word_list(
        source,
        paths.wordlists,
        refresh=args.refresh_word_list,
        offline=args.offline,
    )
    words = tuple(
        word
        for word in result.words
        if (args.min_rank is None or word.rank >= args.min_rank)
        and (args.max_rank is None or word.rank <= args.max_rank)
    )
    if args.limit is not None:
        words = words[: args.limit]
    return replace(result, words=words)


def _summary_for_failure(
    spec: BenchmarkSpec,
    *,
    language: str,
    status: str,
    error: str,
    output_dir: Path,
    catalog_source: str | None,
    artifact: Any = None,
    progress: ProgressReporter | None = None,
    phonetic_metadata: dict[str, Any] | None = None,
) -> BenchmarkRunResult:
    if progress is not None:
        progress.stage(spec.lexicon_id, "failed", f"{status}: {error}")
    metadata = {
        "kind": getattr(artifact, "kind", "pronunciation"),
        "phoneme_encoding": getattr(artifact, "phoneme_encoding", None),
        "data_version": getattr(artifact, "data_version", None),
        "release_tag": getattr(artifact, "release_tag", None),
    }
    summary = build_summary(
        (),
        language=language,
        lexicon=spec.lexicon_id,
        lexicon_metadata=metadata,
        provider_name=spec.reference_name,
        report_threshold=spec.report_threshold,
        strong_threshold=spec.strong_threshold,
        catalog_metadata={"source": catalog_source},
        phonetic_metadata=phonetic_metadata,
        status=status,
    )
    summary["error"] = error
    write_reports(output_dir, (), summary)
    return BenchmarkRunResult(status, summary)


def run_spec(
    spec: BenchmarkSpec,
    argv: Sequence[str] | None = None,
    *,
    progress: ProgressReporter | None = None,
) -> BenchmarkRunResult:
    parser = _parser(spec)
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    if progress is None:
        progress = ProgressReporter(enabled=not args.quiet)
    label = spec.lexicon_id
    paths = BenchmarkPaths.default()
    output_dir = args.output_dir or paths.reports / _safe_id(spec.lexicon_id)
    catalog_source = args.catalog
    progress.stage(label, "catalog", "resolving artifact")
    try:
        catalog = load_benchmark_catalog(args.catalog)
        artifact = resolve_artifact(catalog, spec.lexicon_id)
    except (CatalogError, ValueError) as error:
        return _summary_for_failure(
            spec,
            language=spec.reference_language or spec.lexicon_id.split(":", 1)[0],
            status="lexicon_download_failed",
            error=str(error),
            output_dir=output_dir,
            catalog_source=catalog_source,
            progress=progress,
        )

    store = DataStore(args.data_home or paths.data)
    progress.stage(label, "lexicon", "verifying/provisioning")
    resolution: CatalogResolution = provision_artifact(
        artifact, store, install=not args.no_install, offline=args.offline
    )
    if resolution.status != "ready":
        return _summary_for_failure(
            spec,
            language=artifact.language,
            status=resolution.status,
            error=resolution.error or resolution.status,
            output_dir=output_dir,
            catalog_source=catalog_source or "configured catalog",
            artifact=artifact,
            progress=progress,
        )
    progress.stage(label, "lexicon", "ready")
    phonetic_context = create_phonetic_context(artifact.language)
    progress.stage(
        label,
        "phonetic",
        f"{phonetic_context.status}; language={phonetic_context.requested_language}",
    )
    if args.require_phonodist and not phonetic_context.active:
        return _summary_for_failure(
            spec,
            language=artifact.language,
            status=(
                "phonetic_profile_unavailable"
                if phonetic_context.status == "profile_unavailable"
                else "phonetic_unavailable"
            ),
            error=phonetic_context.error or phonetic_context.status,
            output_dir=output_dir,
            catalog_source=catalog_source or "configured catalog",
            artifact=artifact,
            progress=progress,
            phonetic_metadata=phonetic_context.as_dict(),
        )

    progress.stage(label, "word list", "preparing")
    try:
        word_list = _word_list_result(args, spec, artifact.language, paths)
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        return _summary_for_failure(
            spec,
            language=artifact.language,
            status="word_list_download_failed",
            error=str(error),
            output_dir=output_dir,
            catalog_source=catalog_source or "configured catalog",
            artifact=artifact,
            progress=progress,
        )
    progress.stage(label, "word list", f"{word_list.spec.id}; {len(word_list.words)} words")

    progress.stage(label, "reference", f"initializing {args.reference}")
    try:
        provider = create_reference(args.reference)
    except ProviderUnavailableError as error:
        return _summary_for_failure(
            spec,
            language=artifact.language,
            status="reference_unavailable",
            error=str(error),
            output_dir=output_dir,
            catalog_source=catalog_source or "configured catalog",
            artifact=artifact,
            progress=progress,
        )
    except (ProviderError, ValueError) as error:
        return _summary_for_failure(
            spec,
            language=artifact.language,
            status="reference_unavailable",
            error=str(error),
            output_dir=output_dir,
            catalog_source=catalog_source or "configured catalog",
            artifact=artifact,
            progress=progress,
        )
    provider_info = provider_spec(
        provider, language=args.reference_language or artifact.language, lexicon_id=artifact.id
    )
    progress.stage(
        label,
        "reference",
        f"ready: {provider_info.name}; version={provider_info.version or 'unavailable'}",
    )

    engine = Phonemizer(
        artifact.language,
        lexicons=[artifact.id],
        store=store,
        fallback=None,
    )
    try:
        rows = collect_validation_rows(
            word_list.words,
            language=args.reference_language or artifact.language,
            engine=engine,
            provider=provider,
            provider_info=provider_info,
            ignore_stress=args.ignore_stress,
            strong_threshold=args.strong_threshold,
            progress=progress,
            phonetic_context=phonetic_context,
            progress_lexicon_id=label,
        )
    finally:
        engine.close()
    attach_phonetic_explanations(
        rows,
        context=phonetic_context,
        report_threshold=args.report_threshold,
    )

    metadata = dict(resolution.metadata or {})
    catalog_metadata = {
        "source": catalog_source or "configured catalog",
        "data_version": artifact.data_version,
        "release_tag": artifact.release_tag,
    }
    word_metadata = {
        "source_id": word_list.spec.id,
        "url": word_list.spec.url,
        "revision": word_list.spec.revision,
        "format": word_list.spec.format,
        "license_note": word_list.spec.license_note,
        "download_sha256": word_list.download_sha256,
        "ranked_sha256": word_list.ranked_sha256,
        "retrieved_at": word_list.retrieved_at,
        "rejected_rows": word_list.rejected_rows,
        "rejected_phrases": word_list.rejected_phrases,
    }
    summary = build_summary(
        rows,
        language=artifact.language,
        lexicon=artifact.id,
        reference_version=provider_info.version,
        word_list_source=word_list.spec.id,
        word_list_limit=args.limit,
        word_list_sha256=word_list.download_sha256,
        word_list_retrieved_date=word_list.retrieved_at,
        lexicon_metadata=metadata,
        ignore_stress=args.ignore_stress,
        report_threshold=args.report_threshold,
        strong_threshold=args.strong_threshold,
        provider_name=provider_info.name,
        provider_encoding=provider_info.source_encoding,
        reference_relationship=provider_info.relationship,
        catalog_metadata=catalog_metadata,
        word_list_metadata=word_metadata,
        phonetic_metadata=phonetic_context.as_dict(),
        module=spec.lexicon_id,
    )
    progress.stage(label, "reports", "writing")
    write_reports(output_dir, rows, summary)
    coverage = summary["coverage"]
    comparison = summary["comparison"]
    phonetic = comparison.get("phonetic", {})
    phonetic_status = summary.get("phonetic", {}).get("status", "not_run")
    progress.stage(
        label,
        "completed",
        f"{coverage['found']}/{coverage['tested']} found; "
        f"{comparison['compared']} legacy compared; "
        f"{phonetic.get('compared', 0)} phonetic compared; "
        f"mean broad distance={comparison['mean_broad_distance']}; "
        f"mean phonetic distance={phonetic.get('mean_distance')}; "
        f"phonetic={phonetic_status}",
    )
    return BenchmarkRunResult("completed", summary, tuple(rows))


def main_for(spec: BenchmarkSpec, argv: Sequence[str] | None = None) -> int:
    try:
        result = run_spec(spec, argv)
    except KeyboardInterrupt:
        print(
            f"[{spec.lexicon_id}] interrupted during benchmark processing",
            file=sys.stderr,
            flush=True,
        )
        print("pronunciation validation interrupted by user", file=sys.stderr, flush=True)
        return 130
    summary = result.summary
    coverage = summary["coverage"]
    comparison = summary["comparison"]
    phonetic = comparison.get("phonetic", {})
    phonetic_status = summary.get("phonetic", {}).get("status", "not_run")
    print(
        f"{spec.lexicon_id}: {result.status}; "
        f"{coverage['found']}/{coverage['tested']} found; "
        f"{comparison['compared']} legacy compared; "
        f"{phonetic.get('compared', 0)} phonetic compared; "
        f"mean broad distance={comparison['mean_broad_distance']}; "
        f"mean phonetic distance={phonetic.get('mean_distance')}; "
        f"phonetic={phonetic_status}"
    )
    return 0 if result.status == "completed" else 2
