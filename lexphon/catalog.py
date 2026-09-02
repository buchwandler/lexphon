from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import CatalogError

DEFAULT_CATALOG_URL = "https://raw.githubusercontent.com/buchwandler/g2lex-data/main/catalog/catalog.json"


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
    def from_dict(cls, value: dict[str, Any]) -> "CatalogArtifact":
        required = ("id", "language", "name", "kind", "phoneme_encoding", "data_version", "release_tag")
        for key in required:
            if not isinstance(value.get(key), str) or not value[key]:
                raise CatalogError(f"artifact field {key!r} must be a non-empty string")
        manifest = value.get("manifest")
        asset = value.get("asset")
        source = value.get("source", {})
        if not isinstance(manifest, dict) or not isinstance(asset, dict) or not isinstance(source, dict):
            raise CatalogError("artifact manifest, asset, and source must be objects")
        for label, item in (("manifest", manifest), ("asset", asset)):
            if not isinstance(item.get("url"), str) or not isinstance(item.get("sha256"), str):
                raise CatalogError(f"artifact {label} requires url and sha256")
        return cls(
            id=value["id"],
            language=value["language"],
            name=value["name"],
            display_name=str(value.get("display_name") or value["name"]),
            kind=value["kind"],
            phoneme_encoding=value["phoneme_encoding"],
            data_version=value["data_version"],
            release_tag=value["release_tag"],
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
    def from_dict(cls, value: dict[str, Any]) -> "Catalog":
        if value.get("catalog_version") != 1:
            raise CatalogError(f"unsupported catalog_version: {value.get('catalog_version')!r}")
        contract = value.get("runtime_contract")
        if contract != "g2lex-data.catalog.v1":
            raise CatalogError(f"unsupported runtime_contract: {contract!r}")
        raw = value.get("artifacts")
        if not isinstance(raw, list):
            raise CatalogError("catalog artifacts must be a list")
        artifacts = tuple(CatalogArtifact.from_dict(item) for item in raw if isinstance(item, dict))
        if len(artifacts) != len(raw):
            raise CatalogError("catalog artifacts must be objects")
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
        key = language.casefold()
        return tuple(item for item in self.artifacts if item.language.casefold() == key)


def _read_location(location: str) -> bytes:
    parsed = urlparse(location)
    if parsed.scheme in {"http", "https", "file"}:
        with urllib.request.urlopen(location, timeout=30) as response:  # noqa: S310 - explicit catalog URL
            return response.read()
    return Path(location).expanduser().read_bytes()


def load_catalog(location: str | None = None) -> Catalog:
    source = location or os.environ.get("LEXPHON_CATALOG_URL") or DEFAULT_CATALOG_URL
    try:
        value = json.loads(_read_location(source).decode("utf-8"))
    except Exception as exc:  # keep a stable public error at the catalog boundary
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError(f"unable to load catalog from {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError("catalog root must be an object")
    return Catalog.from_dict(value)
