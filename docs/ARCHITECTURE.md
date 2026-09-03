# Lexphon architecture

## Boundaries

The runtime ownership chain is:

```text
g2lex-data -> G2Lex -> Lexphon -> application adapters
```

`g2lex-data` is the producer and publisher. It obtains, transforms, validates, licenses, reproduces, and publishes immutable generic pronunciation data releases. G2Lex is the storage primitive that represents, packs, opens, and queries typed lexicon data. Lexphon is the generic runtime consumer. KokoroG2P is a downstream model adapter.

Lexphon owns catalog consumption, explicit verified installation, immutable local asset storage, language profiles, candidate generation, ordered layered lookup, selectors, pronunciation alphabet normalization, token provenance, CLI behavior, and optional generic fallback engines.

Lexphon does not own source acquisition, dataset transformations, licensing transformations, production dictionary build recipes, Kokoro vocabulary, Kokoro stress or rating policy, or hidden downloads. Lexphon must never contain source acquisition or G2Lex build recipes for production dictionaries.

## Catalog and installation

Lexphon accepts catalog version 1 with runtime contract `g2lex-data.catalog.v1`. Every artifact has a validated logical ID, locale, kind, source encoding, data version, release tag, manifest reference, asset reference, hashes, and asset size. Pronunciation assets use IPA or ARPABET. Membership assets use `none` and are not pronunciation layers.

`DataStore.install()` is the only asset download path and is an explicit network-capable provisioning operation. It downloads and verifies the manifest, validates manifest metadata against the catalog, downloads and verifies the asset, opens it with G2Lex, and moves a complete version into `assets/<logical-id>__<name>/<data-version>/`. A logical ID and data version are immutable. The index is updated atomically. Failed installations remove staging and never register an active partial version.

`installed.json` stores the local manifest and asset paths plus language, kind, encoding, versions, release tag, hashes, size, and logical hash. `path()`, `metadata()`, `verify()`, and `remove()` use only this local state. A copied store can therefore be opened offline. `Phonemizer`, lookup, token phonemization, and rendering do not load catalogs or access the network.

Data release versions and the Lexphon Python package version are independent. Applications should pin both the Python dependency and the immutable data catalog or release used during provisioning.

## Runtime rule

`Phonemizer(...)` opens only already-installed pronunciation assets. A missing lexicon raises `LexiconNotInstalledError` with an install command. Construction, lookup, token phonemization, and rendering do not download data.

Selected layers are searched in caller order. Within each layer, profile-ordered candidates are searched before moving to the next layer. Profiles provide generic Unicode normalization, apostrophe normalization, and exact, lower, casefold, or title candidates. German uses `de` and `de-de` aliases and defaults to `de-de:gold`. English continues to default to `en-us:gold`; CMUdict must be selected explicitly.

The public result alphabet is IPA and every non-null pronunciation is Unicode NFC. ARPABET is converted with deterministic phone and primary or secondary stress rules. Unknown phones and unsupported encodings raise `UnsupportedAlphabetError`. Structured tokens preserve the original token, selected pronunciation, source category, logical lexicon, matched key, source encoding, ordered IPA variants, selector context, and punctuation state. Unknown words remain explicit when fallback is disabled.

## KokoroG2P integration

KokoroG2P should import the Lexphon Python API, not spawn the CLI:

```python
from lexphon import DataStore, Phonemizer

engine = Phonemizer(
    "de-DE",
    lexicons=["de-de:gold"],
    store=DataStore(),
    fallback=None,
)
```

KokoroG2P converts generic Lexphon IPA to its model vocabulary and applies its own fallback, ratings, stress, and compatibility policy. Lexphon remains independent of KokoroG2P and does not validate or rewrite the Kokoro inventory.
