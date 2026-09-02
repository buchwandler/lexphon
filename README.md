# Lexphon

**Lexphon** is a lexicon-driven phonemizer and CLI built on [G2Lex](https://github.com/buchwandler/g2lex). It consumes released pronunciation assets and returns IPA without producing Kokoro phonemes.

```text
g2lex-data release -> explicit Lexphon install -> local G2Lex lookup -> IPA -> KokoroG2P adapter
```

## Package layout

There is intentionally no `src/` directory. The import package lives at `./lexphon`.

## Install for development

```bash
python -m pip install -e ".[dev]"
pytest
```

## Data management

Catalog access and downloads are explicit. `Phonemizer`, lookup, token phonemization, and local store inspection never fetch data.

```bash
lexphon data available de-DE
lexphon data install de-de:gold
lexphon data list
lexphon data info de-de:gold
lexphon data verify de-de:gold
lexphon data remove de-de:gold
```

Use `--catalog PATH_OR_URL` and `--data-home PATH` for a local release or alternate store. Installation downloads the manifest first, verifies manifest and asset hashes and sizes, checks catalog and manifest identity, opens the G2Lex asset, and atomically activates a complete version. Installed metadata is sufficient for offline use.

The production German assets are `de-de:gold`, `de-de:crane`, `de-de:espeak`, and `de-de:olaph`. English CMUdict is available as `en-us:cmudict`. Membership assets can be installed for inventory use but cannot be selected as pronunciation layers.

## CLI

```bash
lexphon -v de-DE "Die Leute kommen."
lexphon -v de-DE --lexicon de-de:crane "Die Leute kommen."
lexphon -v de-DE --lexicon de-de:crane --tag DET "die"
lexphon -v en-US --lexicon en-us:cmudict --json "read"
```

JSON output contains the rendered IPA plus structured token fields: original text, pronunciation, source category, output alphabet, source encoding, logical lexicon ID, matched key, ordered IPA variants, selector tag, known status, and punctuation status.

Optional standalone fallback is explicit:

```bash
lexphon -v de-DE --fallback espeak "unbekannteswort"
```

Fallback is disabled by default. Unknown tokens remain visible to downstream applications.

## Python API

```python
from lexphon import DataStore, Phonemizer

store = DataStore()
with Phonemizer("de-DE", lexicons=["de-de:crane"], store=store) as g2p:
    result = g2p.phonemize_tokens("Die Leute")
    for token in result.tokens:
        print(token.text, token.pronunciation, token.source, token.lexicon_id)
```

`phonemize_tokens()` is the integration API. It preserves token-level provenance, selectors, variants, punctuation, and unknown words. IPA is normalized to Unicode NFC. ARPABET and CMU-style pronunciations are converted deterministically to IPA. Unsupported alphabets and invalid pronunciation tokens raise stable Lexphon exceptions.

## KokoroG2P boundary

KokoroG2P should import the Python API, convert returned IPA using its model-specific vocabulary, and apply its own fallback and ratings policy. Lexphon does not import KokoroG2P, perform Kokoro validation, or download dictionaries during phonemization.
