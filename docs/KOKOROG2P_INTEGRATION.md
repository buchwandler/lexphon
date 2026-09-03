# KokoroG2P integration

The dependency direction is:

```text
g2lex-data -> G2Lex assets -> Lexphon -> KokoroG2P
```

KokoroG2P should import Lexphon's Python API. It should not spawn the CLI in its normal runtime path and should provision data separately from runtime startup.

## Provisioning and runtime

Install the desired Lexphon assets explicitly before starting an offline application:

```bash
python -m pip install "lexphon>=0.1.0,<0.2"
lexphon data install de-de:gold
lexphon data verify de-de:gold
```

Runtime code should open an installed local store without downloading data:

```python
from lexphon import DataStore, Phonemizer

engine = Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    store=DataStore(),
    fallback=None,
)
```

Data versions and the Lexphon Python package version are independent. Deployment should pin the catalog or immutable data release during provisioning and pin the Python dependency separately. The runtime image can use a copied, pre-populated `LEXPHON_DATA_HOME` with no catalog or network access.

## Runtime contract

Use `Phonemizer(..., fallback=None)` so unknown tokens remain explicit. For each token:

1. If Lexphon returned IPA, convert it with the language and model-specific IPA-to-Kokoro converter.
2. If the IPA cannot be represented by the target profile, apply KokoroG2P's existing fallback policy.
3. If Lexphon returned an unknown token, invoke KokoroG2P's eSpeak fallback and convert that result.
4. Preserve Kokoro-specific ratings, stress controls, punctuation handling, offsets, diagnostics, and vocabulary validation in KokoroG2P.

Lexphon's optional eSpeak fallback is a generic standalone feature. KokoroG2P must not enable it because application-level source and rating semantics need to distinguish dictionary hits, dictionary misses, unrepresentable IPA, eSpeak fallback, and rule fallback.

Lexphon results are structured. Each token provides the original text, IPA pronunciation, source category, output alphabet, logical lexicon ID, matched key, source encoding, ordered IPA variants, selector tag, known status, and punctuation status. The first variant is primary, but later variants remain available to the application.

## German configuration

German supports `de` and `de-de` aliases and defaults to `de-de:gold`. The application may preserve public names with an alias map:

```python
GERMAN_LEXPHON_IDS = {
    "gold": "de-de:gold",
    "crane": "de-de:crane",
    "espeak": "de-de:espeak",
    "olaph": "de-de:olaph",
}
```

Kokoro's existing German selector normalization remains an application concern. For example, an application can map its `ART` or `PRON` tags to the generic selector expected by G2Lex before calling `engine.lookup(word, tag=tag)`. Lexphon does not know Kokoro or spaCy tag conventions. Caller-supplied lexicon order remains semantic.

English CMUdict is selected explicitly with `en-us:cmudict`; it does not replace the generic `en-us:gold` default.

## Ownership boundary

`g2lex-data` obtains, transforms, validates, licenses, reproduces, and publishes generic pronunciation data. G2Lex stores and queries that data. Lexphon installs, verifies, selects, and normalizes already-published assets. KokoroG2P owns text preparation, token spans, POS mapping, IPA-to-Kokoro conversion, model validation, stress, ratings, and fallback behavior.

Lexphon performs no catalog lookup or dictionary download during construction or phonemization. It does not import KokoroG2P, return Kokoro phonemes, validate the Kokoro inventory, apply model ratings, or decide model-specific stress and fallback behavior. Lexphon must never contain production dictionary source acquisition or G2Lex build recipes.
