# Lexphon

**Lexphon** is a lexicon-driven phonemizer and CLI built on [G2Lex](https://github.com/buchwandler/g2lex). It sits between reusable pronunciation data and application/model-specific phoneme conversion.

```text
g2lex-data                 lexphon                    kokorog2p
-----------                -------                    ---------
sources                    explicit installer         IPA -> Kokoro
provenance        --->      local G2Lex store   --->   model vocabulary
G2Lex builds               layered lookup             Kokoro stress policy
catalog                    IPA normalization          application fallback policy
releases                   optional eSpeak fallback
```

Lexphon deliberately does **not** produce Kokoro phonemes. Its canonical pronunciation output is IPA.

## Package layout

There is intentionally **no `src/` directory**:

```text
lexphon/
    __init__.py
    engine.py
    store.py
    catalog.py
    ...
pyproject.toml
```

## Dynamic versioning

The package uses a small dependency-free Git-derived `_version.py`; `project.version` is not hard-coded. Git tags produce release versions and development checkouts produce derived versions. The standalone MVP ZIP falls back to `0.1.0` because it does not contain `.git` metadata. `LEXPHON_VERSION` can explicitly override the version for controlled builds.

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Data management

Downloads are **always explicit**. Calling `Phonemizer` never performs network I/O.

```bash
lexphon data available de-DE
lexphon data install de-de:gold
lexphon data list
lexphon data verify de-de:gold
lexphon data remove de-de:gold
```

Use `--catalog PATH_OR_URL` and `--data-home PATH` to point at a test release or alternate catalog/store.

## eSpeak-like CLI

```bash
lexphon -v de-DE "Die Leute kommen."
lexphon -v de-DE --lexicon de-de:crane "Die Leute kommen."
echo "Hello world" | lexphon -v en-US
```

For tagged G2Lex values:

```bash
lexphon -v de-DE --lexicon de-de:crane --tag DET "die"
```

Machine-readable output:

```bash
lexphon -v en-US --json "read"
```

Optional standalone fallback:

```bash
lexphon -v de-DE --fallback espeak "unbekannteswort"
```

The fallback is not enabled by default. KokoroG2P can therefore call Lexphon with no fallback and retain its own eSpeak fallback/rating logic.

## Python API

```python
from lexphon import DataStore, Phonemizer

store = DataStore()

with Phonemizer("de-DE", lexicons=["de-de:crane"], store=store) as g2p:
    result = g2p.phonemize_tokens("Die Leute")
    for token in result.tokens:
        print(token.text, token.pronunciation, token.source, token.lexicon_id)
```

`phonemize_tokens()` is the integration API for downstream tools. It keeps token-level provenance and unknown words visible, so a consumer can decide whether and how to fall back.

## MVP alphabet support

- IPA: exact pass-through;
- CMU/ARPABET: normalized to IPA;
- membership lexicons: installable but rejected as pronunciation layers.

Additional source alphabets should be added to `lexphon.alphabets` without changing G2Lex or KokoroG2P.
