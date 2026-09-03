from __future__ import annotations

import hashlib
import shutil
import tarfile
import zipfile
from importlib.resources import files
from pathlib import Path

import g2lex
import pytest

from lexphon import DataStore, Phonemizer

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def _members(path: Path) -> tuple[str, ...]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return tuple(archive.namelist())
    with tarfile.open(path, "r:gz") as archive:
        return tuple(member.name for member in archive.getmembers())


def _package_members(members: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        name for name in members if "/lexphon/" in f"/{name}" or name.startswith("lexphon/")
    )


def test_source_package_has_runtime_resources_and_no_dictionaries() -> None:
    package = ROOT / "lexphon"
    assert (package / "profiles.toml").is_file()
    assert (package / "py.typed").is_file()
    assert not list(package.rglob("*.g2lex"))


def test_built_artifacts_have_runtime_resources_and_no_dictionaries() -> None:
    artifacts = sorted(DIST.glob("lexphon-*.whl")) + sorted(DIST.glob("lexphon-*.tar.gz"))
    if not artifacts:
        pytest.skip("build artifacts are created by the release artifact job")
    assert any(path.suffix == ".whl" for path in artifacts)
    assert any(path.suffix == ".gz" for path in artifacts)
    for artifact in artifacts:
        package = _package_members(_members(artifact))
        assert any(
            name.endswith("/lexphon/profiles.toml") or name == "lexphon/profiles.toml"
            for name in package
        )
        assert any(
            name.endswith("/lexphon/py.typed") or name == "lexphon/py.typed" for name in package
        )
        assert not any(name.endswith(".g2lex") for name in package)


def test_installed_package_opens_a_prepopulated_store_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lexphon

    assert files("lexphon").joinpath("profiles.toml").is_file()
    assert files("lexphon").joinpath("py.typed").is_file()
    assert lexphon.DataStore is DataStore
    source = tmp_path / "fixture.jsonl"
    source.write_text('{"word":"Haus","kind":"scalar","value":"haʊ̯s"}\n', encoding="utf-8")
    asset = tmp_path / "fixture.g2lex"
    g2lex.pack_file(
        source,
        asset,
        input_format="jsonl",
        source_id="packaging-test",
        metadata={"pronunciation_alphabet": "ipa"},
    )
    root = tmp_path / "store"
    asset_path = root / "assets" / "fixture.g2lex"
    asset_path.parent.mkdir(parents=True)
    shutil.copyfile(asset, asset_path)
    manifest_path = root / "manifest.json"
    manifest_path.write_text('{"id":"de-de:fixture"}\n', encoding="utf-8")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    store = DataStore(root)
    store._write_index(
        {
            "schema_version": 1,
            "artifacts": {
                "de-de:fixture": {
                    "id": "de-de:fixture",
                    "language": "de-DE",
                    "name": "fixture",
                    "display_name": "fixture",
                    "kind": "pronunciation",
                    "phoneme_encoding": "ipa",
                    "data_version": "test-1",
                    "release_tag": "data-test-1",
                    "manifest_path": "manifest.json",
                    "asset_path": "assets/fixture.g2lex",
                    "asset_sha256": digest(asset_path),
                    "asset_size": asset_path.stat().st_size,
                    "manifest_sha256": digest(manifest_path),
                }
            },
        }
    )

    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected network access")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    with Phonemizer("de-DE", lexicons=["de-de:fixture"], store=store) as engine:
        assert engine.lookup("Haus").pronunciation == "haʊ̯s"
