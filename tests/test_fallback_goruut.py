import pytest

from lexphon.errors import ProviderExecutionError
from lexphon.providers import GoruutProvider


class FakeGoruut:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def phonemize(self, *, language: str, sentence: str) -> str:
        self.calls.append((language, sentence))
        return "(fr)bɔ̃(de)"


def test_goruut_provider_returns_raw_source_output() -> None:
    client = FakeGoruut()
    result = GoruutProvider(client).phonemize("bonjour", "fr-FR")
    assert result == "(fr)bɔ̃(de)"
    assert client.calls == [("fr-FR", "bonjour")]


def test_goruut_provider_execution_failure_is_explicit() -> None:
    class FailingClient:
        def phonemize(self, **kwargs: str) -> str:
            raise RuntimeError("broken")

    with pytest.raises(ProviderExecutionError, match="execution failed"):
        GoruutProvider(FailingClient()).phonemize("bonjour", "fr-FR")
