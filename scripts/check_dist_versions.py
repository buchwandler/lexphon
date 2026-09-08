from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

_PACKAGE = "lexphon"
_VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']$', re.MULTILINE)


def _metadata_version(content: str, path: Path) -> str:
    metadata = Parser().parsestr(content, headersonly=True)
    if metadata.get("Name", "").casefold() != _PACKAGE:
        raise ValueError(f"{path} does not contain Lexphon metadata")
    version = metadata.get("Version")
    if not version:
        raise ValueError(f"{path} has no package version")
    return version.strip()


def _artifact_version(path: Path) -> str:
    if path.name.endswith(".whl"):
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError(f"{path} must contain exactly one dist-info METADATA file")
            return _metadata_version(archive.read(names[0]).decode("utf-8"), path)
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            names = [
                member
                for member in archive.getmembers()
                if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1
            ]
            if len(names) != 1:
                raise ValueError(f"{path} must contain exactly one PKG-INFO file")
            extracted = archive.extractfile(names[0])
            if extracted is None:
                raise ValueError(f"could not read metadata from {path}")
            return _metadata_version(extracted.read().decode("utf-8"), path)
    raise ValueError(f"unsupported distribution artifact: {path}")


def _source_version(root: Path) -> str:
    path = root / "lexphon" / "_version.py"
    match = _VERSION_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"could not read explicit version from {path}")
    return match.group(1)


def _normalize_tag(tag: str) -> str:
    return tag.removeprefix("refs/tags/").removeprefix("v")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Lexphon source, distribution, and release-tag versions."
    )
    parser.add_argument("artifacts", nargs="+", type=Path)
    parser.add_argument("--tag", help="release tag, such as v0.2.0")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]

    try:
        versions = {"source": _source_version(root)}
        for artifact in args.artifacts:
            versions[str(artifact)] = _artifact_version(artifact)
        tag = args.tag or os.environ.get("GITHUB_REF_NAME")
        if tag:
            versions["release tag"] = _normalize_tag(tag)
    except (OSError, UnicodeError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"version check failed: {error}", file=sys.stderr)
        return 1

    expected = versions["source"]
    mismatches = {label: value for label, value in versions.items() if value != expected}
    for label, value in versions.items():
        print(f"{label}: {value}")
    if mismatches:
        print(f"version mismatch: expected {expected}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
