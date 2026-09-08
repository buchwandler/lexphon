# Lexphon

Lexphon is a generic, lexicon-driven phonemizer and CLI built on [G2Lex](https://github.com/buchwandler/g2lex). It consumes released pronunciation assets and returns normalized IPA without producing Kokoro phonemes.

Lexphon provides:

- Ordered, layered lexicon lookup with language profiles and selectors.
- Deterministic IPA and ARPABET normalization.
- Structured token results with pronunciation and provenance metadata.
- Explicit, optional eSpeak and Goruut pronunciation providers.
- Offline runtime behavior after data has been provisioned.

```{toctree}
:maxdepth: 2

ARCHITECTURE
KOKOROG2P_INTEGRATION
MIGRATING_0_2
changelog
```

See the [README](https://github.com/buchwandler/lexphon) for the complete installation instructions, API reference, CLI examples, and data-source boundaries.

## Install

```bash
python -m pip install lexphon
```

Install optional providers separately when needed:

```bash
python -m pip install "lexphon[espeak]"
python -m pip install "lexphon[goruut]"
```

The eSpeak extra expects an eSpeak or eSpeak-NG executable supplied by the operating system. Pygoruut may provision its own Goruut runtime.

## Quick start

Provision a pronunciation asset before using profile defaults:

```bash
lexphon data install de-de:gold
lexphon phonemize --language de-DE "Die Leute kommen."
```

The Python API exposes both lexical evidence and staged pronunciation lookup:

```python
from lexphon import Phonemizer

with Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    fallback=None,
) as engine:
    result = engine.phonemize_tokens("Die Leute")
    for token in result.tokens:
        print(token.text, token.pronunciation, token.source)
```

`lookup_lexicon()` searches only installed lexicons. `lookup()` searches lexicons first and invokes the configured provider only after a miss. Runtime commands do not download catalogs or lexicons implicitly.

## Data lifecycle

Catalog access and downloads are explicit. `DataStore.install()` retrieves and verifies a manifest and asset, then activates the complete version atomically. `list`, `info`, `verify`, and `remove` inspect or manage local data without network access.

Data release versions and the Lexphon Python package version are independent. Pin both the Python dependency and the immutable data release used during provisioning.
