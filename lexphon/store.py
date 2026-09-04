from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import g2lex

from .catalog import _ID_RE, CatalogArtifact
from .errors import DataDownloadError, DataIntegrityError, LexiconNotInstalledError

_DATA_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def default_data_home() -> Path:
    configured = os.environ.get("LEXPHON_DATA_HOME")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "lexphon"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lexphon"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "lexphon"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_data_version(value: str) -> str:
    if not _DATA_VERSION_RE.fullmatch(value):
        raise DataIntegrityError(f"invalid data version: {value!r}")
    return value


def _download(
    url: str,
    target: Path,
    *,
    artifact: CatalogArtifact,
    resource: str,
) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
    except urllib.error.HTTPError as exc:
        raise DataDownloadError(
            identifier=artifact.id,
            resource=resource,
            url=url,
            release_tag=artifact.release_tag,
            data_version=artifact.data_version,
            status_code=exc.code,
            reason=str(exc.reason),
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DataDownloadError(
            identifier=artifact.id,
            resource=resource,
            url=url,
            release_tag=artifact.release_tag,
            data_version=artifact.data_version,
            reason=str(exc),
        ) from exc


class DataStore:
    """Local immutable asset store. Downloads occur only through explicit install()."""

    def __init__(self, root: str | Path | None = None):
        self.root = (Path(root).expanduser() if root is not None else default_data_home()).resolve()
        self.assets_root = self.root / "assets"
        self.index_path = self.root / "installed.json"

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.is_file():
            return {"schema_version": 1, "artifacts": {}}
        try:
            value = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise DataIntegrityError(
                f"invalid Lexphon store index {self.index_path}: {exc}"
            ) from exc
        if not isinstance(value, dict) or value.get("schema_version", 1) != 1:
            raise DataIntegrityError(f"invalid Lexphon store index: {self.index_path}")
        artifacts = value.get("artifacts")
        if not isinstance(artifacts, dict):
            raise DataIntegrityError(f"invalid Lexphon store index: {self.index_path}")
        return value

    def _write_index(self, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = self.index_path.with_name(f".{self.index_path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with temp.open("r+b") as handle:
                os.fsync(handle.fileno())
            os.replace(temp, self.index_path)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _safe_asset_dir(identifier: str, data_version: str) -> tuple[str, str]:
        if not _ID_RE.fullmatch(identifier):
            raise DataIntegrityError(f"invalid logical lexicon ID: {identifier!r}")
        return identifier.replace(":", "__"), _validate_data_version(data_version)

    @staticmethod
    def _safe_filename(value: object, label: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or Path(value).name != value
            or value in {".", ".."}
        ):
            raise DataIntegrityError(f"invalid {label} filename: {value!r}")
        return value

    def _version_dir(self, identifier: str, data_version: str) -> Path:
        safe_id, safe_version = self._safe_asset_dir(identifier, data_version)
        path = (self.assets_root / safe_id / safe_version).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise DataIntegrityError(f"asset path escapes data root for {identifier}") from exc
        return path

    def _local_path(self, relative: object, identifier: str) -> Path:
        if not isinstance(relative, str) or not relative:
            raise DataIntegrityError(f"invalid local path for installed lexicon {identifier}")
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise DataIntegrityError(f"installed path escapes data root for {identifier}") from exc
        return path

    def install(self, artifact: CatalogArtifact) -> Path:
        data_version = _validate_data_version(artifact.data_version)
        version_dir = self._version_dir(artifact.id, data_version)
        asset_name = self._safe_filename(artifact.asset.get("name"), "asset")
        manifest_name = self._safe_filename(artifact.manifest.get("name"), "manifest")
        asset_path = version_dir / asset_name
        manifest_path = version_dir / manifest_name
        index = self._read_index()
        existing = index["artifacts"].get(artifact.id)
        if isinstance(existing, dict) and existing.get("data_version") == data_version:
            expected = {
                "language": artifact.language,
                "name": artifact.name,
                "kind": artifact.kind,
                "phoneme_encoding": artifact.phoneme_encoding,
                "release_tag": artifact.release_tag,
                "asset_sha256": artifact.asset["sha256"],
                "asset_size": artifact.asset["size"],
                "manifest_sha256": artifact.manifest["sha256"],
            }
            if artifact.asset.get("logical_sha256") is not None:
                expected["logical_sha256"] = artifact.asset["logical_sha256"]
            if any(key in existing and existing[key] != value for key, value in expected.items()):
                raise DataIntegrityError(
                    f"lexicon {artifact.id!r} data version {data_version!r} is immutable"
                )
        if version_dir.exists():
            if (
                version_dir.is_dir()
                and asset_path.is_file()
                and manifest_path.is_file()
                and self._verify_files(artifact, asset_path, manifest_path)
            ):
                self._register(artifact, asset_path, manifest_path)
                return asset_path
            raise DataIntegrityError(
                f"lexicon {artifact.id!r} data version {data_version!r} is immutable"
            )
        self.assets_root.mkdir(parents=True, exist_ok=True)
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".install-", dir=self.assets_root))
        try:
            staged_manifest = stage / manifest_name
            staged_asset = stage / asset_name
            _download(
                str(artifact.manifest["url"]),
                staged_manifest,
                artifact=artifact,
                resource="manifest",
            )
            self._verify_manifest_hash(artifact, staged_manifest)
            manifest = self._read_manifest(staged_manifest, artifact)
            _download(
                str(artifact.asset["url"]),
                staged_asset,
                artifact=artifact,
                resource="asset",
            )
            self._verify_asset(artifact, staged_asset)
            self._verify_manifest_agreement(artifact, manifest)
            self._verify_g2lex(artifact, staged_asset)
            os.replace(stage, version_dir)
            stage = Path()
            self._register(artifact, asset_path, manifest_path)
            return asset_path
        except (DataIntegrityError, DataDownloadError):
            raise
        except Exception as exc:
            raise DataIntegrityError(f"unable to install lexicon {artifact.id}: {exc}") from exc
        finally:
            if stage != Path() and stage.exists():
                shutil.rmtree(stage, ignore_errors=True)

    def _verify_manifest_hash(self, artifact: CatalogArtifact, manifest_path: Path) -> None:
        expected = artifact.manifest["sha256"]
        if _sha256(manifest_path) != expected:
            raise DataIntegrityError(f"manifest SHA-256 mismatch for {artifact.id}")
        expected_size = artifact.manifest.get("size")
        if expected_size is not None and manifest_path.stat().st_size != expected_size:
            raise DataIntegrityError(f"manifest size mismatch for {artifact.id}")

    def _verify_asset(self, artifact: CatalogArtifact, asset_path: Path) -> None:
        if _sha256(asset_path) != artifact.asset["sha256"]:
            raise DataIntegrityError(f"asset SHA-256 mismatch for {artifact.id}")
        if asset_path.stat().st_size != artifact.asset["size"]:
            raise DataIntegrityError(f"asset size mismatch for {artifact.id}")

    def _read_manifest(self, manifest_path: Path, artifact: CatalogArtifact) -> dict[str, Any]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise DataIntegrityError(f"invalid manifest for {artifact.id}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise DataIntegrityError(f"manifest for {artifact.id} must be an object")
        if manifest.get("id") != artifact.id:
            raise DataIntegrityError(f"manifest id does not match catalog for {artifact.id}")
        legacy_hash = manifest.get("asset_sha256")
        if legacy_hash is not None and legacy_hash != artifact.asset["sha256"]:
            raise DataIntegrityError(
                f"manifest asset hash does not match catalog for {artifact.id}"
            )
        if "contract_version" in manifest:
            required = (
                "contract_version",
                "manifest_version",
                "data_version",
                "kind",
                "language",
                "name",
                "phoneme_encoding",
            )
            if any(key not in manifest for key in required):
                raise DataIntegrityError(f"manifest is missing required metadata for {artifact.id}")
            if manifest["contract_version"] != 1 or manifest["manifest_version"] != 1:
                raise DataIntegrityError(f"unsupported manifest contract for {artifact.id}")
        return manifest

    def _verify_manifest_agreement(
        self, artifact: CatalogArtifact, manifest: dict[str, Any]
    ) -> None:
        for key in ("id", "data_version", "kind", "phoneme_encoding"):
            if key in manifest and manifest[key] != getattr(artifact, key):
                raise DataIntegrityError(f"catalog and manifest {key} disagree for {artifact.id}")
        manifest_language = manifest.get("language")
        if manifest_language is not None and manifest_language.casefold().replace(
            "_", "-"
        ) != artifact.language.casefold().replace("_", "-"):
            raise DataIntegrityError(f"catalog and manifest language disagree for {artifact.id}")
        manifest_name = manifest.get("name")
        if manifest_name is not None and manifest_name != artifact.name:
            raise DataIntegrityError(f"catalog and manifest name disagree for {artifact.id}")
        asset = manifest.get("asset")
        if isinstance(asset, dict):
            expected = {"sha256": artifact.asset["sha256"], "size": artifact.asset["size"]}
            for key, value in expected.items():
                if key in asset and asset[key] != value:
                    raise DataIntegrityError(
                        f"catalog and manifest asset {key} disagree for {artifact.id}"
                    )
            logical_hash = artifact.asset.get("logical_sha256")
            if logical_hash and asset.get("logical_sha256") not in {None, logical_hash}:
                raise DataIntegrityError(
                    f"catalog and manifest logical hash disagree for {artifact.id}"
                )
        for key in ("asset_sha256", "logical_sha256"):
            if key in manifest:
                expected_value = artifact.asset.get("sha256" if key == "asset_sha256" else key)
                if expected_value is not None and manifest[key] != expected_value:
                    raise DataIntegrityError(
                        f"catalog and manifest {key} disagree for {artifact.id}"
                    )

    def _verify_g2lex(self, artifact: CatalogArtifact, asset_path: Path) -> None:
        try:
            with g2lex.open(asset_path) as lexicon:
                len(lexicon)
                source_encoding = lexicon.metadata.get("source", {}).get("pronunciation_alphabet")
                if (
                    source_encoding is not None
                    and source_encoding.casefold() != artifact.phoneme_encoding
                ):
                    raise DataIntegrityError(
                        f"G2Lex encoding does not match catalog for {artifact.id}"
                    )
        except DataIntegrityError:
            raise
        except Exception as exc:
            raise DataIntegrityError(
                f"G2Lex asset cannot be opened for {artifact.id}: {exc}"
            ) from exc

    def _verify_files(
        self, artifact: CatalogArtifact, asset_path: Path, manifest_path: Path
    ) -> bool:
        try:
            self._verify_manifest_hash(artifact, manifest_path)
            manifest = self._read_manifest(manifest_path, artifact)
            self._verify_asset(artifact, asset_path)
            self._verify_manifest_agreement(artifact, manifest)
            self._verify_g2lex(artifact, asset_path)
        except (DataIntegrityError, OSError):
            return False
        return True

    def _register(self, artifact: CatalogArtifact, asset_path: Path, manifest_path: Path) -> None:
        index = self._read_index()
        artifacts = index["artifacts"]
        metadata = {
            "id": artifact.id,
            "language": artifact.language,
            "name": artifact.name,
            "display_name": artifact.display_name,
            "kind": artifact.kind,
            "phoneme_encoding": artifact.phoneme_encoding,
            "data_version": artifact.data_version,
            "release_tag": artifact.release_tag,
            "manifest_path": str(manifest_path.relative_to(self.root)),
            "asset_path": str(asset_path.relative_to(self.root)),
            "asset_sha256": artifact.asset["sha256"],
            "asset_size": artifact.asset["size"],
            "manifest_sha256": artifact.manifest["sha256"],
        }
        if artifact.asset.get("logical_sha256"):
            metadata["logical_sha256"] = artifact.asset["logical_sha256"]
        artifacts[artifact.id] = metadata
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
        path = self._local_path(metadata.get("asset_path"), identifier)
        if not path.is_file():
            raise LexiconNotInstalledError(
                f"installed lexicon file is missing for {identifier}: {path}"
            )
        return path

    def verify(self, identifier: str) -> bool:
        metadata = self.metadata(identifier)
        try:
            asset = self._local_path(metadata.get("asset_path"), identifier)
            manifest = self._local_path(metadata.get("manifest_path"), identifier)
            if not asset.is_file() or not manifest.is_file():
                return False
            if _sha256(asset) != metadata.get("asset_sha256") or _sha256(manifest) != metadata.get(
                "manifest_sha256"
            ):
                return False
            with g2lex.open(asset) as lexicon:
                len(lexicon)
        except (DataIntegrityError, OSError, ValueError, g2lex.LexiconFormatError):
            return False
        return True

    def remove(self, identifier: str) -> None:
        index = self._read_index()
        metadata = index["artifacts"].pop(identifier, None)
        if metadata is None:
            return
        asset_path = self._local_path(metadata.get("asset_path"), identifier)
        shutil.rmtree(asset_path.parent, ignore_errors=True)
        self._write_index(index)
