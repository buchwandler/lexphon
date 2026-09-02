# Lexphon architecture

## Boundaries

G2Lex is the storage primitive. `g2lex-data` is the producer and publisher. Lexphon is the generic pronunciation runtime. KokoroG2P is a downstream model adapter.

Lexphon owns catalog consumption, explicit verified installation, immutable local asset storage, language profiles, candidate generation, ordered layered lookup, selectors, pronunciation alphabet normalization, token provenance, CLI behavior, and optional generic fallback engines.

Lexphon does not own source acquisition, dataset transformations, licensing transformations, Kokoro vocabulary, Kokoro stress or rating policy, or hidden downloads.

## Catalog and installation

Lexphon accepts catalog version 1 with runtime contract `g2lex-data.catalog.v1`. Every artifact has a validated logical ID, locale, kind, source encoding, data version, release tag, manifest reference, asset reference, hashes, and asset size. Pronunciation assets use IPA or ARPABET. Membership assets use `none` and are not pronunciation layers.

`DataStore.install()` is the only asset download path. It downloads and verifies the manifest, validates manifest metadata against the catalog, downloads and verifies the asset, opens it with G2Lex, and moves a complete version into `assets/<logical-id>__<name>/<data-version>/`. The index is updated atomically. Failed installations remove staging and never register an active partial version.

`installed.json` stores the local manifest and asset paths plus language, kind, encoding, versions, release tag, hashes, size, and logical hash. `path()`, `metadata()`, `verify()`, and `remove()` use only this local state. A copied store can therefore be opened offline.

## Runtime rule

`Phonemizer(...)` opens only already-installed pronunciation assets. A missing lexicon raises `LexiconNotInstalledError` with an install command. Construction, lookup, token phonemization, and rendering do not load catalogs or access the network.

For each selected layer in caller order, Lexphon searches every profile-ordered candidate before trying the next layer. Profiles provide generic Unicode normalization, apostrophe normalization, and exact, lower, casefold, or title candidates. German uses `de` and `de-de` aliases and defaults to `de-de:gold`. English continues to default to `en-us:gold`; CMUdict must be selected explicitly.

The public result alphabet is IPA. IPA is NFC-normalized. ARPABET is converted with deterministic phone and primary or secondary stress rules. Unknown phones and unsupported encodings raise `UnsupportedAlphabetError`. Structured tokens preserve the original token, selected pronunciation, source category, logical lexicon, matched key, source encoding, ordered IPA variants, selector context, and punctuation state.

## KokoroG2P integration

KokoroG2P should depend on the Python API, use `fallback=None`, convert Lexphon IPA to its model vocabulary, and apply its own fallback, ratings, stress, and compatibility policy. Lexphon remains independent of KokoroG2P.
