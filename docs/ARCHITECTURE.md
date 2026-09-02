# Lexphon architecture

## Boundaries

G2Lex is the storage primitive. `g2lex-data` is the producer/publisher. Lexphon is the generic pronunciation runtime. KokoroG2P is a downstream model adapter.

Lexphon owns catalog consumption, verified installation, local asset lifecycle, language profiles, case candidates, layered lookup, selector handling, pronunciation-alphabet normalization, token-level provenance, CLI behavior, and optional generic fallback engines.

Lexphon does not own source acquisition/building, upstream licensing transformations, Kokoro's phoneme vocabulary, Kokoro-specific stress controls, or hidden downloads during phonemization.

## Runtime rule

`Phonemizer(...)` is offline with respect to data installation. A missing lexicon raises `LexiconNotInstalledError`. The only network-capable path is explicit `DataStore.install()` / `lexphon data install` (and explicit eSpeak is a local subprocess, not a network operation).

## KokoroG2P integration

KokoroG2P should depend on the Python API rather than spawning the CLI. It should inspect token results, convert Lexphon IPA to Kokoro-compatible symbols, and use its own eSpeak fallback for unknown or Kokoro-incompatible tokens.
