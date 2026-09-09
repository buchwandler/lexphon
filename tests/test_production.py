from __future__ import annotations

import hashlib
import json
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path

import g2lex
import pytest

from lexphon import (
    CatalogError,
    DataDownloadError,
    DataIntegrityError,
    DataStore,
    LexiconNotInstalledError,
    LexiconNotUsableError,
    Phonemizer,
    UnsupportedAlphabetError,
)
from lexphon.alphabets import to_ipa
from lexphon.catalog import Catalog, CatalogArtifact, load_catalog
from lexphon.cli import main
from lexphon.profiles import ProfileRegistry


def test_current_g2lex_v1_fixture_opens() -> None:
    path = Path(__file__).parent / "fixtures" / "g2lex-v1-compat.g2lex"
    with g2lex.open(path) as lexicon:
        assert len(lexicon) == 1
        assert lexicon.get("compatibility") == "kəmˌpætəˈbɪləti"
        assert lexicon.metadata["format"] == "g2lex.lexicon.v1"
        assert lexicon.metadata["schema"] == 1


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
                {"word": "downloaden", "kind": "scalar", "value": "(en)dˈaʊnləʊdən(de)"},
                {"word": "cancel", "kind": "scalar", "value": "(en)kˈansəl(de)"},
                {"word": "download", "kind": "scalar", "value": "(en)dˈaʊnləʊd(de)"},
                {"word": "gecancelt", "kind": "scalar", "value": "ɡəkˈankəlt"},
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
        "en-us:gold": (
            "en",
            "gold-kokoro",
            "kokoro-v1",
            [{"word": "hello", "kind": "scalar", "value": "KOKORO_HELLO"}],
        ),
        "en-us:lexhint": (
            "en-US",
            "lexhint-en-us",
            "ipa",
            [{"word": "hello", "kind": "scalar", "value": "həˈloʊ"}],
        ),
        "en-gb:lexhint": (
            "en-GB",
            "lexhint-en-gb",
            "ipa",
            [{"word": "hello", "kind": "scalar", "value": "həˈləʊ"}],
        ),
        "fr:lexhint": (
            "fr",
            "lexhint-fr",
            "ipa",
            [{"word": "bonjour", "kind": "scalar", "value": "bɔ̃ʒuʁ"}],
        ),
        "ru:lexhint": (
            "ru",
            "lexhint-ru",
            "ipa",
            [{"word": "привет", "kind": "scalar", "value": "prʲɪˈvʲet"}],
        ),
        "ru:lexhint-native": (
            "ru",
            "lexhint-ru-native",
            "ipa",
            [{"word": "привет", "kind": "scalar", "value": "prʲɪˈvʲet"}],
        ),
        "th:lexhint-native": (
            "th",
            "lexhint-th-native",
            "ipa",
            [{"word": "hello", "kind": "scalar", "value": "hɛləʊ"}],
        ),
        "sv-se:nst": ("sv-SE", "nst", "ipa", [{"word": "hej", "kind": "scalar", "value": "hɛj"}]),
        "vi:lexhint": (
            "vi",
            "lexhint-vi",
            "ipa",
            [{"word": "xin", "kind": "scalar", "value": "sin"}],
        ),
        "ja:lexhint": (
            "ja",
            "lexhint-ja",
            "ipa",
            [{"word": "こんにちは", "kind": "scalar", "value": "konnitɕiwa"}],
        ),
        "ko:lexhint": (
            "ko",
            "lexhint-ko",
            "ipa",
            [{"word": "안녕", "kind": "scalar", "value": "an nyeŋ"}],
        ),
        "pt:lexhint": (
            "pt",
            "lexhint-pt",
            "ipa",
            [{"word": "olá", "kind": "scalar", "value": "oˈla"}],
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
            "language": "de-DE" if locale == "de" else "en-US" if locale == "en" else locale,
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
    assert len(catalog.artifacts) == 17
    raw = {"catalog_version": 1, "runtime_contract": "g2lex-data.catalog.v1", "artifacts": []}
    assert Catalog.from_dict(raw).artifacts == ()
    raw["runtime_contract"] = "other"
    with pytest.raises(CatalogError):
        Catalog.from_dict(raw)


def test_mixed_catalog_preserves_application_specific_assets(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    artifact = catalog.artifact("en-us:gold")
    assert artifact.phoneme_encoding == "kokoro-v1"

    store = DataStore(tmp_path / "store")
    store.install(artifact)
    assert store.verify(artifact.id)
    assert store.metadata(artifact.id)["phoneme_encoding"] == "kokoro-v1"
    with pytest.raises(UnsupportedAlphabetError, match="kokoro-v1"):
        Phonemizer("en-US", lexicons=[artifact.id], store=store)


def test_source_variant_logical_ids_parse(release: Path) -> None:
    base = asdict(load_catalog(str(release)).artifact("de-de:gold"))
    for identifier in (
        "ru:lexhint",
        "ru:lexhint-native",
        "de-de:lexhint",
        "de-de:lexhint-native",
        "th:lexhint-native",
    ):
        raw = {**base, "id": identifier, "language": identifier.split(":", 1)[0]}
        parsed = CatalogArtifact.from_dict(raw)
        assert parsed.id == identifier


def test_builtin_defaults_match_producer_contract(release: Path) -> None:
    catalog = load_catalog(str(release))
    expected = {
        "de-DE": ("de-de:gold", "ipa"),
        "en-US": ("en-us:lexhint", "ipa"),
        "en-GB": ("en-gb:lexhint", "ipa"),
        "fr-FR": ("fr:lexhint", "ipa"),
        "sv-SE": ("sv-se:nst", "ipa"),
        "ru": ("ru:lexhint", "ipa"),
        "th": ("th:lexhint-native", "ipa"),
        "vi": ("vi:lexhint", "ipa"),
        "ja": ("ja:lexhint", "ipa"),
        "ko": ("ko:lexhint", "ipa"),
        "pt": ("pt:lexhint", "ipa"),
    }
    profiles = ProfileRegistry()
    for language, (identifier, encoding) in expected.items():
        profile = profiles.resolve(language)
        assert profile.default_lexicons == (identifier,)
        artifact = catalog.artifact(identifier)
        assert artifact.kind == "pronunciation"
        assert artifact.phoneme_encoding == encoding


def test_preferred_native_and_regional_selection(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    for identifier in (
        "ru:lexhint",
        "ru:lexhint-native",
        "th:lexhint-native",
        "fr:lexhint",
        "en-us:cmudict",
    ):
        store.install(catalog.artifact(identifier))

    with Phonemizer("ru", store=store) as engine:
        assert engine.layers[0].identifier == "ru:lexhint"
        assert engine.lookup("привет").lexicon_id == "ru:lexhint"
    with Phonemizer("ru", lexicons=["ru:lexhint-native", "ru:lexhint"], store=store) as engine:
        assert engine.lookup("привет").lexicon_id == "ru:lexhint-native"
    with Phonemizer("th", store=store) as engine:
        assert engine.layers[0].identifier == "th:lexhint-native"
    with Phonemizer("fr-FR", lexicons=["fr:lexhint"], store=store) as engine:
        assert engine.lookup("bonjour").lexicon_id == "fr:lexhint"
    with pytest.raises(LexiconNotUsableError, match="not compatible"):
        Phonemizer("en-GB", lexicons=["en-us:cmudict"], store=store)


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
        assert [variant.pronunciation for variant in engine.lookup("die").variants] == ["diː"]
    with Phonemizer("en-US", lexicons=["en-us:cmudict"], store=store) as engine:
        result = engine.lookup("read")
        assert result.pronunciation == "ˈɹid"
        assert [variant.pronunciation for variant in result.variants] == ["ˈɹid", "ˈɹɛd"]


def test_annotated_production_lookup_and_rendering(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("de-de:gold"))

    with Phonemizer("de-DE", lexicons=["de-de:gold"], store=store) as engine:
        downloaden = engine.lookup("downloaden")
        assert downloaden.pronunciation == "dˈaʊnləʊdən"
        assert downloaden.source_pronunciation == "(en)dˈaʊnləʊdən(de)"
        assert tuple(marker.language for marker in downloaden.language_markers) == ("en", "de")
        assert engine.lookup("gecancelt").language_markers == ()
        assert engine.phonemize_tokens("downloaden").render() == "dˈaʊnləʊdən"


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
        assert [variant.pronunciation for variant in result.variants] == [
            to_ipa(value, artifact.phoneme_encoding) for value in raw_variants
        ]
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


@pytest.mark.parametrize("asset_path", ["victim.g2lex", "assets/victim.g2lex"])
def test_remove_rejects_shallow_index_paths(asset_path: str, tmp_path: Path) -> None:
    store = DataStore(tmp_path / "store")
    store.root.mkdir(parents=True)
    (store.root / "keep.txt").write_text("keep", encoding="utf-8")
    store.assets_root.mkdir()
    (store.assets_root / "keep.txt").write_text("keep", encoding="utf-8")
    store._write_index(
        {
            "schema_version": 1,
            "artifacts": {
                "de-de:gold": {
                    "data_version": "2026.09.0",
                    "asset_path": asset_path,
                    "manifest_path": "assets/de-de__gold/2026.09.0/manifest.json",
                }
            },
        }
    )

    with pytest.raises(DataIntegrityError, match="do not match"):
        store.remove("de-de:gold")

    assert (store.root / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert (store.assets_root / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert store.metadata("de-de:gold")["asset_path"] == asset_path


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
                "phonemize",
                "--language",
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
    assert payload["schema_version"] == 2
    assert payload["tokens"][0]["source_encoding"] == "arpabet"
    assert payload["tokens"][0]["lexicon_id"] == "en-us:cmudict"


def test_cli_json_and_plain_output_use_clean_annotated_ipa(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("de-de:gold"))

    assert (
        main(
            [
                "phonemize",
                "--language",
                "de-DE",
                "--data-home",
                str(store.root),
                "--lexicon",
                "de-de:gold",
                "--json",
                "downloaden",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    token = payload["tokens"][0]
    assert token["pronunciation"] == "dˈaʊnləʊdən"
    assert token["variants"][0]["pronunciation"] == "dˈaʊnləʊdən"
    assert token["source_pronunciation"] == "(en)dˈaʊnləʊdən(de)"
    assert token["language_markers"] == [
        {"language": "en", "ipa_offset": 0},
        {"language": "de", "ipa_offset": len("dˈaʊnləʊdən")},
    ]
    assert token["variants"][0]["language_markers"] == token["language_markers"]

    assert (
        main(
            [
                "phonemize",
                "--language",
                "de-DE",
                "--data-home",
                str(store.root),
                "--lexicon",
                "de-de:gold",
                "downloaden",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "dˈaʊnləʊdən\n"


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


def test_rejects_cross_language_lexicon_layer(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("en-us:cmudict"))
    with pytest.raises(LexiconNotUsableError, match="not compatible"):
        Phonemizer("de-DE", lexicons=["en-us:cmudict"], store=store)


def test_accepts_normalized_same_locale(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("de-de:gold"))
    index = json.loads(store.index_path.read_text(encoding="utf-8"))
    index["artifacts"]["de-de:gold"]["language"] = "de_DE"
    _write_json(store.index_path, index)
    with Phonemizer("de-de", lexicons=["de-de:gold"], store=store) as engine:
        assert engine.lookup("Haus").known


def test_constructor_closes_open_layers_after_later_failure(
    release: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    for identifier in ("de-de:gold", "de-de:crane"):
        store.install(catalog.artifact(identifier))

    opened: list[object] = []

    class TrackedLexicon:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def fake_open(path: object) -> TrackedLexicon:
        if opened:
            raise RuntimeError("simulated open failure")
        lexicon = TrackedLexicon()
        opened.append(lexicon)
        return lexicon

    monkeypatch.setattr("lexphon.engine.g2lex.open", fake_open)
    with pytest.raises(RuntimeError, match="simulated open failure"):
        Phonemizer(
            "de-DE",
            lexicons=["de-de:gold", "de-de:crane"],
            store=store,
        )
    assert opened and opened[0].closed


def test_same_id_and_data_version_cannot_change_content(release: Path, tmp_path: Path) -> None:
    catalog = load_catalog(str(release))
    artifact = catalog.artifact("de-de:gold")
    store = DataStore(tmp_path / "store")
    path = store.install(artifact)
    original_bytes = path.read_bytes()
    original_index = store.index_path.read_bytes()
    changed = artifact.__class__(
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
    with pytest.raises(DataIntegrityError, match="immutable"):
        store.install(changed)
    assert path.read_bytes() == original_bytes
    assert store.index_path.read_bytes() == original_index
    assert store.verify(artifact.id)


def test_install_rejects_traversal_asset_name(release: Path, tmp_path: Path) -> None:
    artifact = load_catalog(str(release)).artifact("de-de:gold")
    unsafe = artifact.__class__(
        artifact.id,
        artifact.language,
        artifact.name,
        artifact.display_name,
        artifact.kind,
        artifact.phoneme_encoding,
        artifact.data_version,
        artifact.release_tag,
        artifact.manifest,
        {**artifact.asset, "name": "../escape.g2lex"},
        artifact.source,
    )
    with pytest.raises(DataIntegrityError, match="invalid asset filename"):
        DataStore(tmp_path / "store").install(unsafe)


def test_malformed_store_index_is_a_stable_integrity_error(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "store")
    store.root.mkdir()
    store.index_path.write_text("{", encoding="utf-8")
    with pytest.raises(DataIntegrityError, match="invalid Lexphon store index"):
        store.installed()


def test_fallback_pronunciation_is_nfc(release: Path, tmp_path: Path) -> None:
    artifact = load_catalog(str(release)).artifact("de-de:gold")
    store = DataStore(tmp_path / "store")
    store.install(artifact)

    class DecomposedFallback:
        name = "decomposed"
        source_encoding = "ipa"

        def phonemize(self, text: str, language: str) -> str:
            return "e\u0301"

    with Phonemizer(
        "de-DE",
        lexicons=[artifact.id],
        store=store,
        fallback=DecomposedFallback(),
    ) as engine:
        token = engine.lookup("missing", tag="NOUN")
    assert token.pronunciation == "é"
    assert token.pronunciation == unicodedata.normalize("NFC", token.pronunciation or "")
    assert token.variants[0].pronunciation == "é"


def test_manifest_download_404_has_structured_context(
    release: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = load_catalog(str(release)).artifact("de-de:gold")
    store = DataStore(tmp_path / "store")

    def fail(url: str, timeout: int) -> object:
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(DataDownloadError) as caught:
        store.install(artifact)

    error = caught.value
    assert error.identifier == artifact.id
    assert error.resource == "manifest"
    assert error.release_tag == artifact.release_tag
    assert error.data_version == artifact.data_version
    assert error.status_code == 404
    assert error.url == artifact.manifest["url"]
    assert not store.index_path.exists()
    assert not store._version_dir(artifact.id, artifact.data_version).exists()
    assert not list(store.assets_root.glob("**/.install-*"))


def test_asset_download_404_has_asset_context(
    release: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = load_catalog(str(release)).artifact("de-de:gold")
    store = DataStore(tmp_path / "store")
    original_urlopen = urllib.request.urlopen

    def fail_asset(url: str, timeout: int) -> object:
        if url == artifact.asset["url"]:
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return original_urlopen(url, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", fail_asset)
    with pytest.raises(DataDownloadError) as caught:
        store.install(artifact)

    assert caught.value.resource == "asset"
    assert caught.value.identifier == artifact.id
    assert not store.installed()
    assert not store._version_dir(artifact.id, artifact.data_version).exists()
    assert not list(store.assets_root.glob("**/.install-*"))


def test_network_download_failure_is_not_integrity_error(
    release: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = load_catalog(str(release)).artifact("de-de:gold")
    store = DataStore(tmp_path / "store")

    def fail(url: str, timeout: int) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(DataDownloadError) as caught:
        store.install(artifact)

    assert caught.value.status_code is None
    assert caught.value.resource == "manifest"
    assert caught.value.reason is not None
    assert "connection refused" in caught.value.reason


def test_root_help_lists_discoverable_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--help"])

    assert caught.value.code == 0
    output = capsys.readouterr().out
    assert all(word in output for word in ("phonemize", "data", "languages"))
    assert "lexphon data install" in output


def test_data_help_describes_commands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["data", "--help"])

    assert caught.value.code == 0
    output = capsys.readouterr().out
    assert "available" in output
    assert "List lexicons declared by the selected catalog" in output
    assert "does not prove" in output
    assert all(word in output for word in ("install", "list", "info", "verify", "remove"))


def test_data_install_help_describes_atomic_workflow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["data", "install", "--help"])

    assert caught.value.code == 0
    output = capsys.readouterr().out.lower()
    assert all(
        word in output for word in ("id", "downloads", "verify", "atomically", "failed install")
    )


def test_data_empty_states_are_explicit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data", "--data-home", str(tmp_path), "list"]) == 0
    assert capsys.readouterr().out.strip() == "No lexicons installed."

    assert main(["data", "--data-home", str(tmp_path), "verify"]) == 0
    assert "nothing to verify" in capsys.readouterr().out.lower()


def test_available_no_match_is_explicit(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["data", "--catalog", str(release), "available", "fr-XX"]) == 0
    assert "No catalog entries found for language 'fr-XX'." in capsys.readouterr().out


def test_available_shows_logical_id_and_display_name(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["data", "--catalog", str(release), "available", "ru"]) == 0
    output = capsys.readouterr().out
    assert "ru:lexhint\tlexhint-ru\tru\tipa" in output
    assert "ru:lexhint-native\tlexhint-ru-native\tru\tipa" in output


def test_cli_download_404_is_actionable(
    release: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = json.loads(release.read_text(encoding="utf-8"))
    raw["artifacts"][0]["manifest"]["url"] = "https://example.invalid/missing.manifest.json"
    catalog_path = tmp_path / "404-catalog.json"
    _write_json(catalog_path, raw)

    def fail(url: str, timeout: int) -> object:
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert (
        main(
            [
                "data",
                "--catalog",
                str(catalog_path),
                "--data-home",
                str(tmp_path / "store"),
                "install",
                "de-de:gold",
            ]
        )
        == 2
    )

    error = capsys.readouterr().err
    assert all(
        value in error
        for value in (
            "de-de:gold",
            "manifest",
            "2026.09.0",
            "404",
            "URL",
            "catalog entry",
            "not available",
            "failed lexicon was not installed",
        )
    )


def test_cli_partial_install_failure_does_not_claim_nothing_installed(
    release: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed = tmp_path / "installed.g2lex"
    calls = 0

    def install(_store: DataStore, artifact: object) -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            return installed
        assert isinstance(artifact, CatalogArtifact)
        raise DataDownloadError(
            identifier=artifact.id,
            resource="manifest",
            url="https://example.invalid/missing",
            release_tag=artifact.release_tag,
            data_version=artifact.data_version,
            reason="missing",
        )

    monkeypatch.setattr(DataStore, "install", install)
    assert (
        main(
            [
                "data",
                "--catalog",
                str(release),
                "--data-home",
                str(tmp_path / "store"),
                "install",
                "de-de:gold",
                "de-de:crane",
            ]
        )
        == 2
    )

    captured = capsys.readouterr()
    assert "installed de-de:gold" in captured.out
    assert "The failed lexicon was not installed." in captured.err
    assert "Nothing was installed." not in captured.err


def test_explicit_phonemize_form_is_supported_and_legacy_form_is_rejected(
    release: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = load_catalog(str(release))
    store = DataStore(tmp_path / "store")
    store.install(catalog.artifact("en-us:cmudict"))

    assert (
        main(
            [
                "phonemize",
                "--language",
                "en-US",
                "--data-home",
                str(store.root),
                "--lexicon",
                "en-us:cmudict",
                "hello",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "həˈloʊ\n"

    with pytest.raises(SystemExit):
        main(["-v", "en-US", "hello"])
    with pytest.raises(SystemExit):
        main(["voices"])
