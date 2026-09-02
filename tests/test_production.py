from __future__ import annotations

import hashlib
import json
from pathlib import Path

import g2lex
import pytest

from lexphon import (
    CatalogError,
    DataIntegrityError,
    DataStore,
    LexiconNotInstalledError,
    LexiconNotUsableError,
    Phonemizer,
)
from lexphon.alphabets import to_ipa
from lexphon.catalog import Catalog, load_catalog
from lexphon.cli import main
from lexphon.profiles import ProfileRegistry


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _release(tmp_path: Path) -> Path:
    release = tmp_path / "release"
    release.mkdir()
    definitions = {
        "de-de:gold": (
            "de",
            "gold",
            "ipa",
            [
                {"word": "haus", "kind": "scalar", "value": "gold"},
                {"word": "die", "kind": "tagged", "items": [["DEFAULT", "diː"], ["DET", "deː"]]},
            ],
        ),
        "de-de:crane": (
            "de",
            "crane",
            "ipa",
            [
                {"word": "Haus", "kind": "scalar", "value": "crane"},
                {"word": "mädchen", "kind": "scalar", "value": "mɛːtçən"},
            ],
        ),
        "de-de:espeak": (
            "de",
            "espeak",
            "ipa",
            [{"word": "haus", "kind": "scalar", "value": "espeak"}],
        ),
        "de-de:olaph": (
            "de",
            "olaph",
            "ipa",
            [{"word": "haus", "kind": "scalar", "value": "olaph"}],
        ),
        "en-us:cmudict": (
            "en",
            "cmudict",
            "arpabet",
            [
                {"word": "hello", "kind": "scalar", "value": "HH AH0 L OW1"},
                {"word": "read", "kind": "list", "value": ["R IY1 D", "R EH1 D"]},
            ],
        ),
    }
    artifacts = []
    for identifier, (locale, name, encoding, records) in definitions.items():
        source = release / f"{name}.jsonl"
        source.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
            encoding="utf-8",
        )
        asset = release / f"g2lex-{identifier.replace(':', '-')}.g2lex"
        input_format = "jsonl"
        g2lex.pack_file(
            source,
            asset,
            input_format=input_format,
            source_id=identifier,
            metadata={"pronunciation_alphabet": encoding},
        )
        manifest = release / f"{asset.stem}.manifest.json"
        manifest_value = {
            "asset": {
                "filename": asset.name,
                "name": asset.name,
                "sha256": _sha(asset),
                "size": asset.stat().st_size,
                "logical_sha256": "0" * 64,
            },
            "contract_version": 1,
            "data_version": "2026.09.0",
            "id": identifier,
            "kind": "pronunciation",
            "language": "de-DE" if locale == "de" else "en-US",
            "manifest_version": 1,
            "name": name,
            "phoneme_encoding": encoding,
        }
        _write_json(manifest, manifest_value)
        artifacts.append(
            {
                "id": identifier,
                "language": manifest_value["language"],
                "name": name,
                "display_name": name,
                "kind": "pronunciation",
                "phoneme_encoding": encoding,
                "data_version": "2026.09.0",
                "release_tag": "data-test-2026.09.0",
                "manifest": {
                    "name": manifest.name,
                    "url": manifest.as_uri(),
                    "sha256": _sha(manifest),
                    "size": manifest.stat().st_size,
                },
                "asset": {
                    "name": asset.name,
                    "url": asset.as_uri(),
                    "sha256": _sha(asset),
                    "size": asset.stat().st_size,
                    "format": "g2lex.lexicon.v1",
                    "logical_sha256": "0" * 64,
                },
                "source": {"provider": "test", "revision": "1", "license_expression": "CC0-1.0"},
            }
        )
    catalog = release / "catalog.json"
    _write_json(
        catalog,
        {"catalog_version": 1, "runtime_contract": "g2lex-data.catalog.v1", "artifacts": artifacts},
    )
    return catalog


@pytest.fixture
def release(tmp_path: Path) -> Path:
    return _release(tmp_path)


def test_catalog_contract_validation(release: Path) -> None:
    catalog = load_catalog(str(release))
    assert len(catalog.artifacts) == 5
    raw = {"catalog_version": 1, "runtime_contract": "g2lex-data.catalog.v1", "artifacts": []}
    assert Catalog.from_dict(raw).artifacts == ()
    raw["runtime_contract"] = "other"
    with pytest.raises(CatalogError):
        Catalog.from_dict(raw)


def test_install_metadata_and_offline_runtime(
    release: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    for artifact in catalog.artifacts:
        store.install(artifact)
    metadata = store.metadata("de-de:gold")
    assert {
        "id",
        "language",
        "kind",
        "phoneme_encoding",
        "data_version",
        "release_tag",
        "manifest_path",
        "asset_path",
        "asset_sha256",
        "asset_size",
        "logical_sha256",
    } <= metadata.keys()

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected network access")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    assert store.path("de-de:gold").is_file()
    assert store.verify("de-de:gold")
    with Phonemizer("de-DE", store=store) as engine:
        assert engine.lookup("Haus").pronunciation == "gold"
        assert engine.lookup("Haus").lexicon_id == "de-de:gold"


def test_layer_order_selectors_and_variants(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    for identifier in ("de-de:gold", "de-de:crane", "de-de:espeak", "de-de:olaph", "en-us:cmudict"):
        store.install(catalog.artifact(identifier))
    with Phonemizer("de-DE", lexicons=["de-de:gold", "de-de:crane"], store=store) as engine:
        assert engine.lookup("Haus").pronunciation == "gold"
        assert engine.lookup("Mädchen").pronunciation == "mɛːtçən"
        assert engine.lookup("die", tag="DET").pronunciation == "deː"
        assert engine.lookup("die").variants == ("diː",)
    with Phonemizer("en-US", lexicons=["en-us:cmudict"], store=store) as engine:
        result = engine.lookup("read")
        assert result.pronunciation == "ˈɹid"
        assert result.variants == ("ˈɹid", "ˈɹɛd")


def test_german_direct_lookup_parity(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    for identifier in ("de-de:gold", "de-de:crane", "de-de:espeak", "de-de:olaph"):
        artifact = catalog.artifact(identifier)
        store.install(artifact)
        word = "Haus"
        with g2lex.open(store.path(identifier)) as lexicon:
            candidates = ProfileRegistry().resolve("de-DE").candidates(word)
            matched = next(
                (candidate for candidate in candidates if lexicon.get(candidate) is not None), None
            )
            assert matched is not None
            raw_variants = g2lex.pronunciation_variants(lexicon.get(matched))
        with Phonemizer("de-DE", lexicons=[identifier], store=store) as engine:
            result = engine.lookup(word)
        assert result.lexicon_id == identifier
        assert result.matched_key == matched
        assert result.variants == tuple(
            to_ipa(value, artifact.phoneme_encoding) for value in raw_variants
        )
        assert result.source_encoding == artifact.phoneme_encoding


def test_membership_and_lifecycle(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    artifact = catalog.artifact("de-de:gold")
    store.install(artifact)
    store.remove(artifact.id)
    with pytest.raises(LexiconNotInstalledError):
        store.path(artifact.id)
    store.install(artifact)
    membership_id = "de-de:membership"
    store._write_index(
        {
            "schema_version": 1,
            "artifacts": {membership_id: {"kind": "membership", "phoneme_encoding": "none"}},
        }
    )
    with pytest.raises(LexiconNotUsableError):
        Phonemizer("de-DE", lexicons=[membership_id], store=store)


def test_cli_info_and_structured_json(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("en-us:cmudict"))
    assert main(["data", "--data-home", str(store.root), "info", "en-us:cmudict"]) == 0
    assert '"phoneme_encoding": "arpabet"' in capsys.readouterr().out
    assert (
        main(
            [
                "-v",
                "en-US",
                "--data-home",
                str(store.root),
                "--lexicon",
                "en-us:cmudict",
                "--json",
                "hello",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tokens"][0]["source_encoding"] == "arpabet"
    assert payload["tokens"][0]["lexicon_id"] == "en-us:cmudict"


def test_failed_install_does_not_activate(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    artifact = catalog.artifact("de-de:gold")
    broken = artifact.__class__(
        artifact.id,
        artifact.language,
        artifact.name,
        artifact.display_name,
        artifact.kind,
        artifact.phoneme_encoding,
        artifact.data_version,
        artifact.release_tag,
        artifact.manifest,
        {**artifact.asset, "sha256": "f" * 64},
        artifact.source,
    )
    store = DataStore(tmp_path / "store")
    with pytest.raises(DataIntegrityError):
        store.install(broken)
    assert store.installed() == ()
    assert not list(store.assets_root.glob("**/.install-*"))
