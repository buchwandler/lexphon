from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.pronunciation_validation.model import RankedWord
from benchmarks.pronunciation_validation.phonetic import (
    PhoneticContext,
    attach_phonetic_explanations,
    compare_variants,
    create_phonetic_context,
    phonetic_comparison_metrics,
)
from benchmarks.pronunciation_validation.reporting import build_summary, write_reports
from benchmarks.pronunciation_validation.validation import collect_validation_rows


class FakeEngine:
    def __init__(self, pronunciations: dict[str, tuple[str, ...]]) -> None:
        self.pronunciations = pronunciations

    def lookup_lexicon(self, word: str) -> object:
        variants = self.pronunciations.get(word)
        if variants is None:
            return None
        return SimpleNamespace(
            matched_key=word,
            variants=tuple(
                SimpleNamespace(pronunciation=value, source_pronunciation=value)
                for value in variants
            ),
        )


class FakeProvider:
    name = "fake"
    source_encoding = "ipa"

    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values

    def phonemize_many(self, words: tuple[str, ...], _language: str) -> tuple[str | None, ...]:
        return tuple(self.values[word] for word in words)

    def phonemize(self, word: str, _language: str) -> str | None:
        return self.values[word]


class FakePhonodist:
    class InvalidIPAError(Exception):
        pass

    class UnknownSegmentError(Exception):
        pass

    def __init__(self, scores: dict[str, float], invalid: set[str] | None = None) -> None:
        self.scores = scores
        self.invalid = invalid or set()
        self.explain_calls: list[bool] = []

    def pronunciation_distance(
        self, source: str, _target: str, *, language: str, explain: bool
    ) -> object:
        assert language == "de-DE"
        self.explain_calls.append(explain)
        if source in self.invalid:
            raise self.InvalidIPAError(f"unsupported IPA segment in {source}")
        return SimpleNamespace(
            distance=self.scores[source],
            raw_cost=self.scores[source] * 10,
            denominator=10.0,
            operations=(
                SimpleNamespace(
                    source=(source,),
                    target=("target",),
                    kind="sequence_equivalence",
                    cost=0.1,
                    reason="de-DE:unstressed-schwa-syllabic-nasal",
                ),
            ),
        )


def _context(module: FakePhonodist) -> PhoneticContext:
    return PhoneticContext(
        status="active",
        requested_language="de-DE",
        library="phonodist",
        library_version="0.1.0",
        metric="feature-align",
        metric_version="1",
        profile="de-DE",
        profile_version="1",
        backend="panphon",
        backend_version="test",
        feature_set="spe+",
        stress_policy="ignored_by_metric",
        _module=module,
    )


def test_german_profile_and_representation_pair_are_close() -> None:
    context = create_phonetic_context("de-de")
    assert context.status == "active"
    assert context.profile == "de-DE"
    assert context.metric == "feature-align"
    result = compare_variants(
        ("ˈlʊftvafn̩ˌʃtʏt͡spʊŋkt",),
        "lˈʊftvˌafənʃtˌʏt\u200dspʊŋkt",
        context=context,
    )[0]
    assert result["status"] == "ok"
    assert result["distance"] < 0.10


def test_missing_profile_is_explicit() -> None:
    context = create_phonetic_context("fr")
    assert context.status == "profile_unavailable"
    assert context.profile is None


def test_missing_dependency_is_injectable(monkeypatch: pytest.MonkeyPatch) -> None:
    error = ModuleNotFoundError("No module named 'phonodist'")
    error.name = "phonodist"
    monkeypatch.setattr(
        "benchmarks.pronunciation_validation.phonetic._import_phonodist",
        lambda: (_ for _ in ()).throw(error),
    )
    context = create_phonetic_context("de-DE")
    assert context.status == "dependency_unavailable"
    assert "lexphon[validation]" in (context.error or "")


def test_variant_failures_are_partial_and_selection_is_independent() -> None:
    module = FakePhonodist({"legacy": 0.8, "valid": 0.1}, invalid={"bad"})
    context = _context(module)
    rows = collect_validation_rows(
        [RankedWord(1, "word")],
        language="de-DE",
        engine=FakeEngine({"word": ("bad", "valid")}),
        provider=FakeProvider({"word": "reference"}),
        phonetic_context=context,
    )
    row = rows[0]
    assert row["phonetic_status"] == "ok"
    assert row["phonetic_best_variant_index"] == 1
    assert row["phonetic_variant_results"][0]["status"] == "unsupported_ipa"
    assert row["phonetic_selector_disagrees"] is True


def test_all_invalid_variants_do_not_abort_legacy_scoring() -> None:
    module = FakePhonodist({}, invalid={"bad", "also-bad"})
    context = _context(module)
    row = collect_validation_rows(
        [RankedWord(1, "word")],
        language="de-DE",
        engine=FakeEngine({"word": ("bad", "also-bad")}),
        provider=FakeProvider({"word": "reference"}),
        phonetic_context=context,
    )[0]
    assert row["phonetic_status"] == "unsupported_ipa"
    assert row["phonetic_distance"] is None
    assert row["broad_distance"] is not None
    assert "2/2 variants unsupported" in row["phonetic_error"]


def test_selector_disagreement_and_explanation_second_pass() -> None:
    module = FakePhonodist({"a": 0.0, "b": 0.8})
    context = _context(module)
    rows = collect_validation_rows(
        [RankedWord(1, "word")],
        language="de-DE",
        engine=FakeEngine({"word": ("a", "b")}),
        provider=FakeProvider({"word": "b"}),
        phonetic_context=context,
    )
    row = rows[0]
    assert row["best_variant_index"] == 1
    assert row["phonetic_best_variant_index"] == 0
    assert row["phonetic_selector_disagrees"] is True
    assert module.explain_calls == [False, False]

    attach_phonetic_explanations(rows, context=context, report_threshold=0.30)
    assert module.explain_calls == [False, False, True]
    assert rows[0]["phonetic_operations"][0]["kind"] == "sequence_equivalence"
    assert rows[0]["phonetic_operations"][0]["reason"] == ("de-DE:unstressed-schwa-syllabic-nasal")


def test_phonetic_metrics_and_reports_are_schema_v3(tmp_path: Path) -> None:
    module = FakePhonodist({"a": 0.0, "b": 0.8})
    context = _context(module)
    rows = collect_validation_rows(
        [RankedWord(1, "word")],
        language="de-DE",
        engine=FakeEngine({"word": ("a", "b")}),
        provider=FakeProvider({"word": "b"}),
        phonetic_context=context,
    )
    attach_phonetic_explanations(rows, context=context, report_threshold=0.30)

    metrics = phonetic_comparison_metrics(rows)
    assert metrics["compared"] == 1
    assert metrics["matches"] == 1
    assert metrics["selector_disagreements"] == 1
    summary = build_summary(
        rows,
        language="de-DE",
        lexicon="de-de:fixture",
        phonetic_metadata=context.as_dict(),
    )
    paths = write_reports(tmp_path, rows, summary)
    saved = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert saved["schema_version"] == 3
    assert saved["phonetic"]["profile"] == "de-DE"
    assert saved["comparison"]["phonetic"]["compared"] == 1
    assert paths["selector_disagreements"].is_file()
    assert (
        "phonetic_distance"
        in paths["selector_disagreements"].read_text(encoding="utf-8").splitlines()[0]
    )
    evidence = paths["rows"].read_text(encoding="utf-8")
    assert "phonetic_variant_results" in evidence
    assert "phonetic_operations" in evidence
