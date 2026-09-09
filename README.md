[![PyPI - Version](https://img.shields.io/pypi/v/lexphon)](https://pypi.org/project/lexphon/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/lexphon)
![PyPI - Downloads](https://img.shields.io/pypi/dm/lexphon)
[![codecov](https://codecov.io/gh/buchwandler/lexphon/graph/badge.svg?token=7EteJ0dez8)](https://codecov.io/gh/buchwandler/lexphon)

# Lexphon

**Lexphon** is a generic, lexicon-driven phonemizer and CLI built on [G2Lex](https://github.com/buchwandler/g2lex). It consumes released pronunciation assets and returns normalized IPA without producing Kokoro phonemes.

```text
g2lex-data producer -> G2Lex storage -> Lexphon runtime -> application adapter
```

The ownership boundary is deliberate:

- `g2lex-data` obtains, transforms, validates, licenses, and publishes immutable data releases.
- G2Lex stores and queries typed lexicon data.
- Lexphon explicitly installs, verifies, selects, and consumes released assets.
- KokoroG2P or another application converts generic IPA to its model-specific output.

Lexphon must never contain source acquisition or G2Lex build recipes for production dictionaries.

## Package layout

There is intentionally no `src/` directory. The import package lives at `./lexphon`.

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Data management

Catalog access and downloads are explicit. The user-visible data states are distinct: a catalog declaration is not proof of remote publication, and remote publication is not local installation. `DataStore.install()` is the network-capable provisioning operation. `Phonemizer`, lookup, token phonemization, rendering, and local store inspection never fetch a catalog or download a lexicon.

`lexphon data available` lists artifacts declared by the selected catalog only. It does not download the referenced manifest or asset or verify that release files are reachable. `lexphon data install` retrieves and verifies those files. If a catalog points to a missing release resource, the install diagnostic reports the logical ID, manifest or asset, release tag, data version, URL, and HTTP or connectivity failure, and confirms that the failed lexicon was not installed.

```bash
lexphon data available de-DE
lexphon data install de-de:gold
lexphon data list
lexphon data info de-de:gold
lexphon data verify de-de:gold
lexphon data remove de-de:gold
lexphon phonemize --language de-DE "Die Leute kommen."
```

When upgrading from older built-in defaults, provision the new generic assets explicitly before using `lexicons=None`:

```bash
lexphon data install en-us:lexhint
lexphon data install en-gb:lexhint
lexphon data install fr:lexhint
lexphon data install th:lexhint-native
```

Applications that intentionally need an older `*:gold` application-specific asset should select it explicitly through their downstream integration.

Use `--catalog PATH_OR_URL` and `--data-home PATH` for a local release or alternate store. Installation downloads the manifest first, verifies manifest and asset hashes and sizes, checks catalog and manifest identity, opens the G2Lex asset, and atomically activates a complete version. A copied, pre-populated store eliminates Lexphon catalog and lexicon downloads during runtime. Optional providers have separate provisioning requirements.
The production German assets are `de-de:gold`, `de-de:crane`, `de-de:espeak`, and `de-de:olaph`. English CMUdict is available as the explicit ARPABET alternative `en-us:cmudict`. LexHint logical IDs use `:lexhint` for the preferred/default asset and `:lexhint-native` for an explicit native-Wiktionary alternative. Native-only languages such as Thai use only the native suffix; English's `en-us:lexhint` and `en-gb:lexhint` use native English Wiktionary.

Catalog pronunciation encodings are not all generic Phonemizer alphabets. Lexphon can discover, install, and verify application-specific assets such as `kokoro-v1`, but selecting one as a generic Phonemizer layer raises `UnsupportedAlphabetError`. Kokoro vocabulary conversion remains in KokoroG2P.

Data release versions and the Lexphon Python package version are independent. Pin the data catalog or release during provisioning, and pin the Python dependency separately.

## CLI

```bash
lexphon --help
lexphon languages
lexphon phonemize --language de-DE "Die Leute kommen."
lexphon phonemize --language de-DE --lexicon de-de:crane "Die Leute kommen."
lexphon phonemize --language de-DE --lexicon de-de:crane --tag DET "die"
lexphon phonemize --language en-US --lexicon en-us:cmudict --json "read"
```

JSON output has `schema_version: 2` and contains the rendered IPA plus structured token fields: text, pronunciation, source category, provider, requested language, source encoding, logical lexicon ID, matched key, structured variants, selector tag, known status, punctuation status, and provenance metadata.

Inline language-control markers recognized in IPA source notation are consumed once at the Lexphon normalization boundary. They are removed from `pronunciation` and each variant pronunciation, while `source_pronunciation` and structured `language_markers` preserve the raw source and marker metadata for diagnostics and optional downstream routing.
Optional generic provider use is explicit:

```bash
lexphon phonemize --language de-DE --fallback espeak "unbekannteswort"
```

Install optional providers separately when using them:

```bash
python -m pip install "lexphon[espeak]"
python -m pip install "lexphon[goruut]"
```

The eSpeak extra does not install the system executable; provide eSpeak or eSpeak-NG through the operating system. Goruut/Pygoruut may provision its own runtime, so a pre-populated Lexphon data store does not by itself guarantee fully offline provider startup.

Providers are disabled by default. Unknown tokens remain visible to downstream applications.

## Python API

```python
from lexphon import DataStore, Phonemizer

store = DataStore()
with Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    store=store,
    fallback=None,
) as g2p:
    result = g2p.phonemize_tokens("Die Leute")
    for token in result.tokens:
        print(token.text, token.pronunciation, token.source, token.lexicon_id)
```

`phonemize_tokens()` is the integration API. It preserves token-level provenance, selectors, structured variants, punctuation, and unknown words. IPA is normalized to Unicode NFC. ARPABET and CMU-style pronunciations are converted deterministically to IPA. Unsupported alphabets and invalid pronunciation tokens raise stable Lexphon exceptions.

`PronunciationToken.pronunciation` is derived from the first structured variant. `source_pronunciation` and `language_markers` expose its raw source notation and provenance. Downstream adapters should consume this metadata and must not search returned pronunciations for raw tags such as `(en)` or `(de)`.

`lookup_lexicon(token, tag=...)` searches only lexicons and returns `None` on a miss, so it is safe for lexical evidence and language routing. `lookup(token, tag=...)` searches the lexicons first and then invokes the configured generic provider. Configure `fallback=None`, `fallback="espeak"`, `fallback="goruut"`, or a custom `PronunciationProvider`.

For example, a provider result such as `(en)fˈIl(de)` is returned as clean `fˈIl` while retaining `source="provider"`, `provider="espeak"`, `requested_language="de-de"`, the raw `source_pronunciation`, and markers `en@0` and `de@4`.

### Batch lookup and provider contracts

`lookup_many()` preserves input order and checks every configured lexicon before invoking a provider. A provider receives only the missing tokens, and a runtime-checkable `BatchPronunciationProvider` can handle those misses in one call:

```python
results = engine.lookup_many(["one", "two", "three"])
```

When `fallback="espeak"`, the eSpeak provider is batch-capable: `lookup_many()` invokes eSpeak once for the batch of lexicon misses rather than once per token.

Batch output must contain exactly one `str` or `None` result per submitted miss. Lexphon rejects strings, bytes, non-sequences, wrong cardinality, and malformed elements with `ProviderOutputError`. Provider execution failures raise `ProviderExecutionError`; `None` remains a genuine direct miss. All provider output is normalized at the engine boundary.

### Lexicon configuration

`lexicons=None` uses the language profile's default lexicons. Construction raises `LexiconNotInstalledError` when a required default asset is not installed. `lexicons=[]` explicitly selects no lexicon layers and is the provider-only configuration. Use the empty list in provider-only applications and tests when profile defaults should not be opened.

## KokoroG2P boundary

KokoroG2P should import Lexphon's Python API and configure Lexphon's generic providers when needed. It converts returned IPA using its model-specific vocabulary and applies its own stress, ratings, and diagnostics policy. Lexphon does not import KokoroG2P, perform Kokoro validation, or download dictionaries during phonemization.
