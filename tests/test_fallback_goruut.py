from lexphon.fallback import GoruutFallback


class FakeGoruut:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def phonemize(self, *, language: str, sentence: str) -> str:
        self.calls.append((language, sentence))
        return "(fr)bɔ̃(de)"


def test_goruut_returns_clean_ipa_provenance() -> None:
    client = FakeGoruut()
    result = GoruutFallback(client).phonemize("bonjour", "fr-FR")

    assert result is not None
    assert result.provider == "goruut"
    assert result.pronunciation == "bɔ̃"
    assert result.source_pronunciation == "(fr)bɔ̃(de)"
    assert [(marker.language, marker.ipa_offset) for marker in result.language_markers] == [
        ("fr", 0),
        ("de", 3),
    ]
    assert client.calls == [("fr-FR", "bonjour")]
