# KokoroG2P integration

The dependency direction is:

```text
g2lex-data -> G2Lex assets -> Lexphon -> KokoroG2P
```

KokoroG2P should import Lexphon's Python API. It should not spawn the CLI in its normal runtime path and should provision data separately from runtime startup.

## Provisioning and runtime

Install the desired Lexphon assets explicitly before starting an offline application:

```bash
python -m pip install "lexphon>=0.2.0,<0.3"
lexphon data install de-de:gold
lexphon data verify de-de:gold
```

If the application configures `fallback="goruut"`, install the optional adapter explicitly:

```bash
python -m pip install "lexphon[goruut]"
```

Pygoruut may provision or start its own Goruut runtime. A pre-populated Lexphon data home removes Lexphon catalog and lexicon downloads, but it does not guarantee offline Goruut startup. Provision the optional provider runtime separately when fully offline startup is required.

Runtime code should open an installed local store without downloading data:

```python
from lexphon import Phonemizer

engine = Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    fallback="espeak",
)
```

Data versions and the Lexphon Python package version are independent. Deployment should pin the catalog or immutable data release during provisioning and pin the Python dependency separately. The runtime image can use a copied, pre-populated `LEXPHON_DATA_HOME` with no Lexphon catalog or lexicon downloads. Optional providers have separate provisioning requirements, especially Goruut/Pygoruut.

## Runtime contract

Lexphon exposes two lookup modes:

- `lookup_lexicon(token, tag=...)` searches only configured lexicon layers. Use this method for lexical evidence and language routing. A miss returns `None` and cannot invoke a provider.
- `lookup(token, tag=...)` first performs the lexicon lookup, then invokes the configured provider after a miss. With `fallback=None`, an unknown token returns `None`.

KokoroG2P may configure Lexphon with `fallback="espeak"`, `fallback="goruut"`, or a custom `PronunciationProvider`. Provider output is never lexical evidence. Lexphon returns clean generic IPA, structured variants, provider provenance, and `requested_language`; KokoroG2P converts the pronunciation to its model vocabulary and applies model-specific policy.

Preserve Kokoro-specific ratings, stress controls, punctuation handling, offsets, diagnostics, and vocabulary validation in KokoroG2P.

Lexphon results are structured. Each token provides the original text, derived primary IPA pronunciation, source category, provider, requested language, logical lexicon ID, matched key, source encoding, structured variants, selector tag, known status, punctuation status, and pronunciation provenance.

Lexphon's pronunciation normalization handoff is:

```text
raw source notation -> clean generic IPA -> structured language-marker metadata
```

KokoroG2P consumes the clean `pronunciation` and may use `language_markers` as optional downstream evidence. It must not reparse `source_pronunciation` or search `pronunciation` for raw marker syntax such as `(en)` or `(de)`.

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

`g2lex-data` obtains, transforms, validates, licenses, reproduces, and publishes generic pronunciation data. G2Lex stores and queries that data. Lexphon installs, verifies, selects, normalizes, and provides optional generic pronunciation providers for already-published assets. KokoroG2P owns text preparation, token spans, POS mapping, IPA-to-Kokoro conversion, model validation, stress, ratings, and model-specific policy.

Lexphon performs no catalog lookup or dictionary download during construction or phonemization. It does not import KokoroG2P, return Kokoro phonemes, validate the Kokoro inventory, apply model ratings, or decide model-specific stress and fallback behavior. Lexphon must never contain production dictionary source acquisition or G2Lex build recipes.
