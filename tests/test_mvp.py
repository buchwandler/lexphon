from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import g2lex
import pytest

from lexphon import DataStore, LexiconNotInstalledError, Phonemizer, __version__
from lexphon.alphabets import arpabet_to_ipa
from lexphon.catalog import load_catalog


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_write_index_fsyncs_writable_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DataStore(tmp_path / "store")
    original_fsync = os.fsync

    def fsync(fd: int) -> None:
        os.write(fd, b"")
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    store._write_index({"schema_version": 1, "artifacts": {}})
    assert store.installed() == ()


def _fixture_catalog(tmp_path: Path) -> Path:
    release = tmp_path / "release"
    release.mkdir()
    source = tmp_path / "de.jsonl"
    source.write_text(
        '{"word":"die","kind":"tagged","items":[["DEFAULT","diː"],["DET","diː"]]}\n'
        '{"word":"Leute","kind":"scalar","value":"ˈlɔʏtə"}\n'
        '{"word":"kommen","kind":"scalar","value":"ˈkɔmən"}\n'
        '{"word":"Haus","kind":"scalar","value":"haʊ̯s"}\n',
        encoding="utf-8",
    )
    de_asset = release / "de.g2lex"
    g2lex.pack_file(
        source,
        de_asset,
        input_format="jsonl",
        source_id="test-de",
        metadata={"pronunciation_alphabet": "ipa"},
    )
    de_manifest = release / "de.manifest.json"
    _write_json(de_manifest, {"id": "de-de:demo", "asset_sha256": _sha(de_asset)})

    en_source = tmp_path / "en.dict"
    en_source.write_text(
        "hello  HH AH0 L OW1\nworld  W ER1 L D\nread  R IY1 D\nread(2)  R EH1 D\n", encoding="utf-8"
    )
    en_asset = release / "en.g2lex"
    g2lex.pack_file(
        en_source,
        en_asset,
        input_format="cmudict",
        source_id="test-en",
        metadata={"pronunciation_alphabet": "arpabet"},
    )
    en_manifest = release / "en.manifest.json"
    _write_json(en_manifest, {"id": "en-us:demo-cmu", "asset_sha256": _sha(en_asset)})

    artifacts = []
    for identifier, language, name, encoding, asset, manifest in [
        ("de-de:demo", "de-DE", "demo", "ipa", de_asset, de_manifest),
        ("en-us:demo-cmu", "en-US", "demo-cmu", "arpabet", en_asset, en_manifest),
    ]:
        artifacts.append(
            {
                "id": identifier,
                "language": language,
                "name": name,
                "display_name": name,
                "kind": "pronunciation",
                "phoneme_encoding": encoding,
                "data_version": "test-1",
                "release_tag": "data-test-1",
                "source": {"provider": "test", "revision": "1", "license_expression": "CC0-1.0"},
                "manifest": {
                    "name": manifest.name,
                    "url": manifest.as_uri(),
                    "sha256": _sha(manifest),
                },
                "asset": {
                    "name": asset.name,
                    "url": asset.as_uri(),
                    "sha256": _sha(asset),
                    "size": asset.stat().st_size,
                    "format": "g2lex",
                    "schema": 1,
                    "entry_count": 1,
                    "logical_sha256": "0" * 64,
                },
            }
        )
    catalog = tmp_path / "catalog.json"
    _write_json(
        catalog,
        {"catalog_version": 1, "runtime_contract": "g2lex-data.catalog.v1", "artifacts": artifacts},
    )
    return catalog


def _installed_store(tmp_path: Path) -> DataStore:
    catalog = load_catalog(str(_fixture_catalog(tmp_path)))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("de-de:demo"))
    store.install(catalog.artifact("en-us:demo-cmu"))
    return store


def test_dynamic_version_is_exposed() -> None:
    assert isinstance(__version__, str) and __version__


def test_install_is_explicit_and_verified(tmp_path: Path) -> None:
    catalog = load_catalog(str(_fixture_catalog(tmp_path)))
    store = DataStore(tmp_path / "store")
    with pytest.raises(LexiconNotInstalledError):
        store.path("de-de:demo")
    path = store.install(catalog.artifact("de-de:demo"))
    assert path.is_file()
    assert store.verify("de-de:demo")


def test_german_typed_lookup_and_structured_tokens(tmp_path: Path) -> None:
    store = _installed_store(tmp_path)
    with Phonemizer("de-DE", lexicons=["de-de:demo"], store=store) as engine:
        hit = engine.lookup("Die", tag="DET")
        assert hit.pronunciation == "diː"
        assert hit.matched_key == "die"
        assert hit.lexicon_id == "de-de:demo"
        result = engine.phonemize_tokens("Die Leute kommen.", tag="DET")
        assert result.render() == "diː ˈlɔʏtə ˈkɔmən."
        assert result.tokens[-1].punctuation


def test_arpabet_is_normalized_to_ipa_and_variants_survive(tmp_path: Path) -> None:
    assert arpabet_to_ipa("HH AH0 L OW1") == "həˈloʊ"
    store = _installed_store(tmp_path)
    with Phonemizer("en-US", lexicons=["en-us:demo-cmu"], store=store) as engine:
        hello = engine.lookup("Hello")
        assert hello.pronunciation == "həˈloʊ"
        read = engine.lookup("read")
        assert read.variants == ("ˈɹid", "ˈɹɛd")


def test_unknowns_remain_visible_for_kokorog2p_fallback(tmp_path: Path) -> None:
    store = _installed_store(tmp_path)
    with Phonemizer("de-DE", lexicons=["de-de:demo"], store=store) as engine:
        result = engine.phonemize_tokens("Haus Quux")
        assert result.tokens[0].pronunciation == "haʊ̯s"
        assert result.tokens[1].source == "unknown"
        assert result.render(unknown="keep") == "haʊ̯s Quux"


class _FakeFallback:
    def phonemize(self, text: str, language: str) -> str | None:
        return "fəˈbæk" if text == "Quux" else None


def test_optional_fallback_is_generic_and_explicit(tmp_path: Path) -> None:
    store = _installed_store(tmp_path)
    with Phonemizer(
        "de-DE", lexicons=["de-de:demo"], store=store, fallback=_FakeFallback()
    ) as engine:
        token = engine.lookup("Quux")
        assert token.source == "fallback"
        assert token.pronunciation == "fəˈbæk"


def test_missing_default_lexicon_does_not_trigger_download(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "store")
    with pytest.raises(LexiconNotInstalledError):
        Phonemizer("de-DE", store=store)
