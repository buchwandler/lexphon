from types import SimpleNamespace

from lexphon.fallback import EspeakFallback


def test_espeak_returns_clean_ipa_provenance(monkeypatch) -> None:
    monkeypatch.setattr(
        "lexphon.fallback.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="(en)fˈIl(de)"),
    )

    result = EspeakFallback("/fake/espeak").phonemize("File", "de-DE")

    assert result is not None
    assert result.pronunciation == "fˈIl"
    assert result.provider == "espeak"
    assert result.provider_language == "de-DE"
    assert result.source_pronunciation == "(en)fˈIl(de)"
    assert [(marker.language, marker.ipa_offset) for marker in result.language_markers] == [
        ("en", 0),
        ("de", 4),
    ]
