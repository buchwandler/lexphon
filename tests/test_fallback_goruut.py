import pytest

from lexphon.errors import ProviderExecutionError
from lexphon.providers import GoruutProvider


class FakeResponse:
    def __str__(self) -> str:
        return "(fr)bɔ̃(de)"


class FakeGoruut:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def phonemize(self, *, language: str, sentence: str) -> FakeResponse:
        self.calls.append((language, sentence))
        return FakeResponse()


def test_goruut_provider_returns_raw_source_output() -> None:
    client = FakeGoruut()
    result = GoruutProvider(client).phonemize("bonjour", "fr-FR")
    assert result == "(fr)bɔ̃(de)"
    assert client.calls == [("fr", "bonjour")]


@pytest.mark.parametrize(
    ("language", "expected"),
    [("de-DE", "de"), ("fr-FR", "fr"), ("en-US", "EnglishAmerican"), ("en-GB", "EnglishBritish")],
)
def test_goruut_provider_adapts_language_identifiers(language: str, expected: str) -> None:
    client = FakeGoruut()
    GoruutProvider(client).phonemize("bonjour", language)
    assert client.calls == [(expected, "bonjour")]


def test_goruut_provider_rejects_unsupported_language() -> None:
    with pytest.raises(ProviderExecutionError, match="does not support language"):
        GoruutProvider(FakeGoruut()).phonemize("bonjour", "xx-YY")


def test_goruut_provider_execution_failure_is_explicit() -> None:
    class FailingClient:
        def phonemize(self, **kwargs: str) -> str:
            raise RuntimeError("broken")

    with pytest.raises(ProviderExecutionError, match="execution failed"):
        GoruutProvider(FailingClient()).phonemize("bonjour", "fr-FR")
