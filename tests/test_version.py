from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import lexphon._version as version


@pytest.mark.parametrize(
    ("description", "expected"),
    (
        ("v1.2.3-0-gabc123", "1.2.3"),
        ("1.2.3-0-gabc123", "1.2.3"),
        ("v1.2.3-4-gabc123", "1.2.3.post4+gabc123"),
        ("v1.2.3-0-gabc123-dirty", "1.2.3.dev0+gabc123.dirty"),
        ("v1.2.3-dirty", "1.2.3.dev0+dirty"),
    ),
)
def test_get_version_formats_git_describe_values(
    monkeypatch: pytest.MonkeyPatch, description: str, expected: str
) -> None:
    monkeypatch.delenv("LEXPHON_VERSION", raising=False)
    monkeypatch.setattr(version.subprocess, "check_output", lambda *args, **kwargs: description)

    assert version.get_version() == expected


def test_get_version_accepts_unprefixed_tag_and_requests_both_git_patterns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command: list[str] = []

    def check_output(args: list[str], **kwargs: object) -> str:
        command.extend(args)
        return "0.2.0-0-gabc123"

    monkeypatch.delenv("LEXPHON_VERSION", raising=False)
    monkeypatch.setattr(version.subprocess, "check_output", check_output)

    assert version.get_version() == "0.2.0"
    assert "v[0-9]*" in command
    assert "[0-9]*" in command
    assert command.count("--match") == 2


def test_get_version_uses_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXPHON_VERSION", "8.7.6")
    monkeypatch.setattr(
        version.subprocess,
        "check_output",
        lambda *args, **kwargs: pytest.fail("Git should not be queried"),
    )

    assert version.get_version() == "8.7.6"


def test_sdist_version_returns_none_without_pkg_info(tmp_path: Path) -> None:
    assert version._sdist_version(tmp_path) is None


@pytest.mark.parametrize(
    "content",
    (
        "Name: other\nVersion: 9.9.9\n",
        "Name: lexphon\n",
    ),
)
def test_sdist_version_rejects_missing_or_wrong_metadata(tmp_path: Path, content: str) -> None:
    (tmp_path / "PKG-INFO").write_text(content, encoding="utf-8")

    assert version._sdist_version(tmp_path) is None


def test_sdist_version_extracts_valid_metadata(tmp_path: Path) -> None:
    (tmp_path / "PKG-INFO").write_text("Name: lexphon\nVersion: 1.2.3\n", encoding="utf-8")

    assert version._sdist_version(tmp_path) == "1.2.3"


def test_get_version_falls_back_to_sdist_metadata_for_invalid_git_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEXPHON_VERSION", raising=False)
    monkeypatch.setattr(version.subprocess, "check_output", lambda *args, **kwargs: "not-a-version")
    monkeypatch.setattr(version, "_sdist_version", lambda root: "2.3.4")

    assert version.get_version() == "2.3.4"


@pytest.mark.parametrize(
    "error", (OSError("git unavailable"), subprocess.SubprocessError("git failed"))
)
def test_get_version_falls_back_to_sdist_metadata_when_git_fails(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.delenv("LEXPHON_VERSION", raising=False)

    def check_output(*args: object, **kwargs: object) -> str:
        raise error

    monkeypatch.setattr(version.subprocess, "check_output", check_output)
    monkeypatch.setattr(version, "_sdist_version", lambda root: "2.3.4")

    assert version.get_version() == "2.3.4"
