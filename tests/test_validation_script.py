from __future__ import annotations
# ruff: noqa: I001

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


_spec = importlib.util.spec_from_file_location(
    "validate_pronunciations_integration",
    Path(__file__).parents[1] / "scripts" / "validate_pronunciations.py",
)
assert _spec and _spec.loader
_validation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _validation
_spec.loader.exec_module(_validation)


class FakeEngine:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.lookups: list[str] = []

    def lookup_lexicon(self, word: str) -> object:
        self.lookups.append(word)
        return self.values.get(word)


class FakeProvider:
    name = "fake-espeak"
    source_encoding = "ipa"

    def __init__(self, values: dict[str, str | None]) -> None:
        self.values = values
        self.batch_calls: list[tuple[str, ...]] = []

    def phonemize_many(self, words: tuple[str, ...], _language: str) -> tuple[str | None, ...]:
        self.batch_calls.append(words)
        return tuple(self.values[word] for word in words)

    def phonemize(self, word: str, _language: str) -> str | None:
        return self.values[word]


def _token(*pronunciations: str) -> SimpleNamespace:
    return SimpleNamespace(
        matched_key="key",
        variants=tuple(
            SimpleNamespace(pronunciation=value, source_pronunciation=value)
            for value in pronunciations
        ),
    )


def test_ranked_loader_deduplicates_using_best_rank(tmp_path: Path) -> None:
    path = tmp_path / "words.tsv"
    path.write_text("rank\tword\n3\tlate\n1\tfirst\n2\tlate\n\n", encoding="utf-8")
    assert _validation.load_ranked_words(path) == [
        _validation.RankedWord(1, "first"),
        _validation.RankedWord(2, "late"),
    ]

    path.write_text("not-a-rank\tword\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid rank"):
        _validation.load_ranked_words(path)


def test_validation_uses_lexicon_only_and_selects_best_variant() -> None:
    engine = FakeEngine({"Haus": _token("x", "a"), "Foo": _token("z")})
    provider = FakeProvider({"Haus": "a", "Foo": "b"})
    rows = _validation.collect_validation_rows(
        [
            _validation.RankedWord(1, "Haus"),
            _validation.RankedWord(2, "Foo"),
            _validation.RankedWord(3, "Missing"),
        ],
        language="de-DE",
        engine=engine,
        provider=provider,
    )

    assert engine.lookups == ["Haus", "Foo", "Missing"]
    assert provider.batch_calls == [("Haus", "Foo")]
    assert rows[0]["found"] is True
    assert rows[0]["best_variant_index"] == 1
    assert rows[0]["broad_distance"] == 0.0
    assert rows[1]["classification"] == "strong_disagreement"
    assert rows[2]["found"] is False
    assert rows[2]["broad_distance"] is None


def test_reference_miss_is_not_scored() -> None:
    engine = FakeEngine({"Haus": _token("a"), "MissingRef": _token("a")})
    provider = FakeProvider({"Haus": None, "MissingRef": None})
    rows = _validation.collect_validation_rows(
        [_validation.RankedWord(1, "Haus"), _validation.RankedWord(2, "MissingRef")],
        language="de-DE",
        engine=engine,
        provider=provider,
    )
    assert all(row["reference_status"] == "unavailable" for row in rows)
    assert all(row["broad_distance"] is None for row in rows)


def test_batch_reference_failure_falls_back_to_individual_results() -> None:
    class FailingBatchProvider(FakeProvider):
        def phonemize_many(self, words: tuple[str, ...], _language: str) -> tuple[str | None, ...]:
            _ = words
            raise RuntimeError("batch unavailable")

    provider = FailingBatchProvider({"Haus": "a", "Broken": None})
    results = _validation.generate_references(
        ("Haus", "Broken"), language="de-DE", provider=provider
    )
    assert results["Haus"].status == "ok"
    assert results["Broken"].status == "unavailable"


def test_local_word_list_never_downloads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "words.tsv"
    path.write_text("1\tHaus\n", encoding="utf-8")
    args = _validation._parser().parse_args(["--word-list", str(path)])
    monkeypatch.setattr(
        _validation, "_download_word_list", lambda *_args: pytest.fail("downloaded")
    )
    assert _validation._word_list_path(args) == (path, str(path), None)


def test_download_adapter_is_explicit_and_records_ranked_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"Haus\nDie\n"

    monkeypatch.setattr(_validation.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    target = _validation._download_word_list("https://example.test/words", tmp_path / "words.tsv")
    assert target.read_text(encoding="utf-8") == "1\tHaus\n2\tDie\n"


def test_reports_are_deterministic_and_preserve_unrelated_asset(tmp_path: Path) -> None:
    engine = FakeEngine({"Haus": _token("a", "b"), "Foo": _token("z")})
    provider = FakeProvider({"Haus": "b", "Foo": "a"})
    rows = _validation.collect_validation_rows(
        [_validation.RankedWord(1, "Haus"), _validation.RankedWord(2, "Foo")],
        language="de-DE",
        engine=engine,
        provider=provider,
    )
    asset = tmp_path / "installed.g2lex"
    asset.write_bytes(b"immutable fixture")
    before = hashlib.sha256(asset.read_bytes()).digest()
    summary = _validation.build_summary(
        rows,
        language="de-DE",
        lexicon="de-de:gold",
        reference_version=None,
        word_list_source="fixture.tsv",
        word_list_limit=2,
        word_list_sha256="fixture-hash",
        lexicon_metadata={"data_version": "test", "logical_sha256": "logical"},
    )
    summary_path = tmp_path / "validation" / "summary.json"
    csv_path = tmp_path / "validation" / "mismatches.csv"
    _validation.write_summary(summary_path, summary)
    first_csv = _validation.write_mismatches(csv_path, rows, report_threshold=0.30)
    first_summary = summary_path.read_bytes()
    _validation.write_summary(summary_path, summary)
    _validation.write_mismatches(csv_path, rows, report_threshold=0.30)

    assert [row["word"] for row in first_csv] == ["Foo"]
    assert summary_path.read_bytes() == first_summary
    assert json.loads(summary_path.read_text(encoding="utf-8"))["coverage"]["found"] == 2
    assert hashlib.sha256(asset.read_bytes()).digest() == before
