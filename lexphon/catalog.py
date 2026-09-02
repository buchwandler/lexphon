from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import CatalogError

DEFAULT_CATALOG_URL = (
    "https://raw.githubusercontent.com/buchwandler/g2lex-data/main/catalog/catalog.json"
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*:[a-z0-9][a-z0-9._-]*$")
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
_SUPPORTED_KINDS = {"pronunciation", "membership"}
_SUPPORTED_ENCODINGS = {"ipa", "arpabet", "none"}


def _require_text(value: dict[str, Any], key: str, label: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise CatalogError(f"{label} field {key!r} must be a non-empty string")
    return result


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise CatalogError(f"{label} must be a lowercase SHA-256 hash")
    return value


def _require_size(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CatalogError(f"{label} must be a positive integer")
    return value


def _validate_reference(value: object, label: str, *, require_size: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError(f"artifact {label} must be an object")
    url = _require_text(value, "url", f"artifact {label}")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https", "file"} and not parsed.scheme == "":
        raise CatalogError(f"artifact {label} has unsupported URL scheme: {parsed.scheme!r}")
    _require_text(value, "name", f"artifact {label}")
    if Path(value["name"]).name != value["name"] or value["name"] in {".", ".."}:
        raise CatalogError(f"artifact {label} name must be a plain filename")
    _require_hash(value.get("sha256"), f"artifact {label}.sha256")
    if require_size and "size" not in value:
        raise CatalogError(f"artifact {label} requires size")
    if "size" in value:
        _require_size(value["size"], f"artifact {label}.size")
    return value


@dataclass(frozen=True, slots=True)
class CatalogArtifact:
    id: str
    language: str
    name: str
    display_name: str
    kind: str
    phoneme_encoding: str
    data_version: str
    release_tag: str
    manifest: dict[str, Any]
    asset: dict[str, Any]
    source: dict[str, Any]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CatalogArtifact:
        if not isinstance(value, dict):
            raise CatalogError("catalog artifacts must be objects")
        identifier = _require_text(value, "id", "artifact")
        if not _ID_RE.fullmatch(identifier):
            raise CatalogError(f"artifact id is not a valid logical ID: {identifier!r}")
        language = _require_text(value, "language", f"artifact {identifier}")
        normalized_language = language.casefold().replace("_", "-")
        id_language = identifier.split(":", 1)[0]
        if not _LOCALE_RE.fullmatch(normalized_language) or normalized_language != id_language:
            raise CatalogError(f"artifact {identifier} has inconsistent language metadata")
        name = _require_text(value, "name", f"artifact {identifier}")
        if Path(name).name != name:
            raise CatalogError(f"artifact {identifier} name must be a plain name")
        kind = _require_text(value, "kind", f"artifact {identifier}")
        if kind not in _SUPPORTED_KINDS:
            raise CatalogError(f"artifact {identifier} has unsupported kind: {kind!r}")
        encoding = _require_text(value, "phoneme_encoding", f"artifact {identifier}").casefold()
        if encoding not in _SUPPORTED_ENCODINGS:
            raise CatalogError(
                f"artifact {identifier} has unsupported phoneme_encoding: {encoding!r}"
            )
        if kind == "membership" and encoding != "none":
            raise CatalogError(f"membership artifact {identifier} must use phoneme_encoding 'none'")
        if kind == "pronunciation" and encoding == "none":
            raise CatalogError(
                f"pronunciation artifact {identifier} cannot use phoneme_encoding 'none'"
            )
        data_version = _require_text(value, "data_version", f"artifact {identifier}")
        release_tag = _require_text(value, "release_tag", f"artifact {identifier}")
        manifest = _validate_reference(value.get("manifest"), "manifest", require_size=False)
        asset = _validate_reference(value.get("asset"), "asset", require_size=True)
        if asset.get("format") not in {None, "g2lex.lexicon.v1", "g2lex"}:
            raise CatalogError(f"artifact {identifier} has unsupported asset format")
        source = value.get("source", {})
        if not isinstance(source, dict):
            raise CatalogError(f"artifact {identifier} source must be an object")
        return cls(
            id=identifier,
            language=language,
            name=name,
            display_name=str(value.get("display_name") or name),
            kind=kind,
            phoneme_encoding=encoding,
            data_version=data_version,
            release_tag=release_tag,
            manifest=manifest,
            asset=asset,
            source=source,
        )


@dataclass(frozen=True, slots=True)
class Catalog:
    catalog_version: int
    runtime_contract: str
    artifacts: tuple[CatalogArtifact, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Catalog:
        if not isinstance(value, dict):
            raise CatalogError("catalog root must be an object")
        if value.get("catalog_version") != 1:
            raise CatalogError(f"unsupported catalog_version: {value.get('catalog_version')!r}")
        contract = value.get("runtime_contract")
        if contract != "g2lex-data.catalog.v1":
            raise CatalogError(f"unsupported runtime_contract: {contract!r}")
        raw = value.get("artifacts")
        if not isinstance(raw, list):
            raise CatalogError("catalog artifacts must be a list")
        artifacts = tuple(CatalogArtifact.from_dict(item) for item in raw)
        ids = [item.id for item in artifacts]
        if len(set(ids)) != len(ids):
            raise CatalogError("catalog artifact ids must be unique")
        return cls(1, contract, artifacts)

    def artifact(self, identifier: str) -> CatalogArtifact:
        for artifact in self.artifacts:
            if artifact.id == identifier:
                return artifact
        raise CatalogError(f"unknown catalog artifact: {identifier}")

    def for_language(self, language: str) -> tuple[CatalogArtifact, ...]:
        key = language.casefold().replace("_", "-")
        return tuple(
            item for item in self.artifacts if item.language.casefold().replace("_", "-") == key
        )


def _read_location(location: str) -> bytes:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https", "file"}:
        with urllib.request.urlopen(location, timeout=30) as response:
            return response.read()
    return Path(location).expanduser().read_bytes()


def load_catalog(location: str | None = None) -> Catalog:
    source = location or os.environ.get("LEXPHON_CATALOG_URL") or DEFAULT_CATALOG_URL
    try:
        value = json.loads(_read_location(source).decode("utf-8"))
        return Catalog.from_dict(value)
    except CatalogError:
        raise
    except Exception as exc:  # keep a stable public error at the catalog boundary
        raise CatalogError(f"unable to load catalog from {source}: {exc}") from exc
