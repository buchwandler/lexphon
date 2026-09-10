"""Catalog inventory and benchmark-local lexicon provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lexphon.catalog import Catalog, CatalogArtifact, load_catalog
from lexphon.errors import DataDownloadError, DataIntegrityError, LexiconNotInstalledError
from lexphon.store import DataStore

SUPPORTED_ENCODINGS = frozenset({"ipa", "unicodeipa", "arpabet", "cmu", "cmudict"})


@dataclass(frozen=True, slots=True)
class CatalogResolution:
    status: str
    artifact: CatalogArtifact
    metadata: dict[str, Any] | None = None
    path: Path | None = None
    error: str | None = None


def is_fixture_artifact(artifact: CatalogArtifact) -> bool:
    """Exclude deliberately small demo/test artifacts from quality benchmarks."""
    identifier = artifact.id.casefold()
    name = artifact.name.casefold()
    return ":demo" in identifier or "-demo" in identifier or "demo" in name


def is_quality_benchmark_artifact(artifact: CatalogArtifact) -> bool:
    return artifact.kind == "pronunciation" and not is_fixture_artifact(artifact)


def iter_quality_benchmark_artifacts(catalog: Catalog) -> tuple[CatalogArtifact, ...]:
    return tuple(artifact for artifact in catalog.artifacts if is_quality_benchmark_artifact(artifact))


def is_supported_encoding(encoding: str) -> bool:
    return encoding.casefold().replace("-", "") in SUPPORTED_ENCODINGS


def resolve_artifact(catalog: Catalog, identifier: str) -> CatalogArtifact:
    artifact = catalog.artifact(identifier)
    if artifact.kind != "pronunciation":
        raise ValueError(f"catalog artifact {identifier!r} is not a pronunciation lexicon")
    return artifact


def provision_artifact(
    artifact: CatalogArtifact,
    store: DataStore,
    *,
    install: bool = True,
    offline: bool = False,
) -> CatalogResolution:
    if not is_supported_encoding(artifact.phoneme_encoding):
        return CatalogResolution("unsupported_encoding", artifact)
    try:
        metadata = store.metadata(artifact.id)
        path = store.path(artifact.id)
        if not store.verify(artifact.id):
            raise DataIntegrityError(f"installed lexicon {artifact.id!r} failed verification")
        return CatalogResolution("ready", artifact, metadata, path)
    except LexiconNotInstalledError:
        if not install or offline:
            return CatalogResolution("lexicon_not_installed", artifact, error="lexicon is not installed")
    except DataIntegrityError as error:
        return CatalogResolution("lexicon_integrity_failed", artifact, error=str(error))

    try:
        path = store.install(artifact)
        return CatalogResolution("ready", artifact, store.metadata(artifact.id), path)
    except DataDownloadError as error:
        return CatalogResolution("lexicon_download_failed", artifact, error=str(error))
    except DataIntegrityError as error:
        return CatalogResolution("lexicon_integrity_failed", artifact, error=str(error))


def load_benchmark_catalog(location: str | None = None) -> Catalog:
    return load_catalog(location)
