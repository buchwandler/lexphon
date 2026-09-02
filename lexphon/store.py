from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

import g2lex

from .catalog import CatalogArtifact
from .errors import LexiconNotInstalledError, LexphonError


def default_data_home() -> Path:
    configured = os.environ.get("LEXPHON_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "lexphon"
    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lexphon"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lexphon"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_id(identifier: str) -> str:
    return identifier.replace(":", "__").replace("/", "__")


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as output:  # noqa: S310
        shutil.copyfileobj(response, output)


class DataStore:
    """Local immutable asset store. Downloads occur only through explicit install()."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root).expanduser() if root is not None else default_data_home()
        self.assets_root = self.root / "assets"
        self.index_path = self.root / "installed.json"

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.is_file():
            return {"schema_version": 1, "artifacts": {}}
        value = json.loads(self.index_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("artifacts"), dict):
            raise LexphonError(f"invalid Lexphon store index: {self.index_path}")
        return value

    def _write_index(self, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.index_path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, self.index_path)

    def install(self, artifact: CatalogArtifact) -> Path:
        if artifact.kind != "pronunciation" and artifact.kind != "membership":
            raise LexphonError(f"unsupported artifact kind: {artifact.kind}")
        version_dir = self.assets_root / _safe_id(artifact.id) / artifact.data_version
        asset_name = str(artifact.asset["name"])
        manifest_name = str(artifact.manifest["name"])
        asset_path = version_dir / asset_name
        manifest_path = version_dir / manifest_name

        if asset_path.is_file() and manifest_path.is_file():
            if self._verify_files(artifact, asset_path, manifest_path):
                self._register(artifact, asset_path, manifest_path)
                return asset_path

        version_dir.parent.mkdir(parents=True, exist_ok=True)
        stage: Path | None = Path(tempfile.mkdtemp(prefix=".install-", dir=version_dir.parent))
        try:
            assert stage is not None
            staged_asset = stage / asset_name
            staged_manifest = stage / manifest_name
            _download(str(artifact.asset["url"]), staged_asset)
            _download(str(artifact.manifest["url"]), staged_manifest)
            if not self._verify_files(artifact, staged_asset, staged_manifest):
                raise LexphonError(f"download verification failed for {artifact.id}")
            shutil.rmtree(version_dir, ignore_errors=True)
            os.replace(stage, version_dir)
            stage = None
            self._register(artifact, asset_path, manifest_path)
            return asset_path
        finally:
            if stage is not None and stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def _verify_files(self, artifact: CatalogArtifact, asset_path: Path, manifest_path: Path) -> bool:
        if _sha256(asset_path) != artifact.asset["sha256"]:
            return False
        if _sha256(manifest_path) != artifact.manifest["sha256"]:
            return False
        try:
            with g2lex.open(asset_path) as lexicon:
                len(lexicon)
        except Exception:
            return False
        return True

    def _register(self, artifact: CatalogArtifact, asset_path: Path, manifest_path: Path) -> None:
        index = self._read_index()
        artifacts = index["artifacts"]
        artifacts[artifact.id] = {
            "id": artifact.id,
            "language": artifact.language,
            "name": artifact.name,
            "kind": artifact.kind,
            "phoneme_encoding": artifact.phoneme_encoding,
            "data_version": artifact.data_version,
            "asset_path": str(asset_path.relative_to(self.root)),
            "manifest_path": str(manifest_path.relative_to(self.root)),
            "asset_sha256": artifact.asset["sha256"],
            "manifest_sha256": artifact.manifest["sha256"],
        }
        self._write_index(index)

    def installed(self) -> tuple[dict[str, Any], ...]:
        values = self._read_index()["artifacts"]
        return tuple(values[key] for key in sorted(values))

    def metadata(self, identifier: str) -> dict[str, Any]:
        value = self._read_index()["artifacts"].get(identifier)
        if not isinstance(value, dict):
            raise LexiconNotInstalledError(
                f"lexicon {identifier!r} is not installed; run `lexphon data install {identifier}`"
            )
        return value

    def path(self, identifier: str) -> Path:
        metadata = self.metadata(identifier)
        path = self.root / metadata["asset_path"]
        if not path.is_file():
            raise LexiconNotInstalledError(f"installed lexicon file is missing for {identifier}: {path}")
        return path

    def verify(self, identifier: str) -> bool:
        metadata = self.metadata(identifier)
        asset = self.root / metadata["asset_path"]
        manifest = self.root / metadata["manifest_path"]
        if not asset.is_file() or not manifest.is_file():
            return False
        if _sha256(asset) != metadata["asset_sha256"] or _sha256(manifest) != metadata["manifest_sha256"]:
            return False
        try:
            with g2lex.open(asset) as lexicon:
                len(lexicon)
        except Exception:
            return False
        return True

    def remove(self, identifier: str) -> None:
        index = self._read_index()
        metadata = index["artifacts"].pop(identifier, None)
        if metadata is None:
            return
        asset_path = self.root / metadata["asset_path"]
        shutil.rmtree(asset_path.parent, ignore_errors=True)
        self._write_index(index)
