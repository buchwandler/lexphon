# Migrating to Lexphon 0.2

Lexphon 0.2 is a breaking API cleanup. The release makes provider behavior typed and explicit, exposes structured pronunciation variants, and separates Lexphon lexicon provisioning from optional provider provisioning.

## API mapping

| Lexphon 0.1 behavior                                | Lexphon 0.2 replacement                                                               |
| --------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Legacy fallback compatibility APIs                  | Strict `PronunciationProvider` and typed `ProviderError` subclasses                   |
| `variant_details`                                   | Structured `PronunciationToken.variants` and `PronunciationVariant`                   |
| `alphabet`                                          | `source_encoding` at the provider or token boundary, with normalized IPA output       |
| Direct lookup miss with implicit fallback semantics | `None` for a genuine direct miss; providers are invoked only after lexicon misses     |
| Legacy CLI JSON output                              | CLI JSON schema 2 with structured token and provenance fields                         |
| Scalar-only optional provider usage                 | Optional `BatchPronunciationProvider` support through `lookup_many()`                 |
| Implicit or ambiguous default lexicon configuration | `lexicons=None` for profile defaults and `lexicons=[]` for provider-only construction |

## Provider and lexicon configuration

`lexicons=None` opens the language profile's default lexicons and requires those assets to be installed. `lexicons=[]` opens no lexicon layers and is the explicit provider-only configuration. `lookup_many()` checks configured lexicons first, sends only misses to a batch provider when available, preserves input order, and requires one output per submitted miss.

Provider output is normalized at the Lexphon engine boundary. A provider may return `str` or `None` for scalar calls and a sequence of those values for batch calls. Malformed output raises `ProviderOutputError`; provider execution failures raise `ProviderExecutionError`.

Install optional provider dependencies explicitly:

```bash
python -m pip install "lexphon[espeak]"
python -m pip install "lexphon[goruut]"
```

The eSpeak extra does not install the system executable. Pygoruut may provision its own Goruut runtime. A pre-populated `LEXPHON_DATA_HOME` only removes Lexphon catalog and lexicon downloads; it does not guarantee offline startup of an optional provider.

## KokoroG2P adapter example

A 0.1 adapter commonly relied on implicit profile defaults and scalar provider calls:

```python
with Phonemizer("de-DE", fallback="espeak") as engine:
    token = engine.lookup(word)
    if token is not None:
        return convert_ipa_to_kokoro(token.pronunciation or "")
```

In 0.2, choose the lexicon behavior explicitly and preserve typed provider results at the adapter boundary:

```python
from lexphon import Phonemizer
from lexphon.errors import ProviderError

with Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    fallback="espeak",
) as engine:
    try:
        token = engine.lookup(word)
    except ProviderError as error:
        raise LookupError(f"Lexphon provider failed for {word!r}") from error

if token is None:
    raise LookupError(f"Lexphon miss for {word!r}")
return convert_ipa_to_kokoro(token.pronunciation or "")
```

For provider-only operation, replace the lexicon list with `lexicons=[]`. For text batches, use `engine.lookup_many(words)` or `engine.phonemize_tokens(text)` so token order, punctuation, variants, and provenance remain available to the downstream adapter.
