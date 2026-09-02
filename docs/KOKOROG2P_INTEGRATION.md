# KokoroG2P integration

The recommended dependency direction is:

```text
g2lex-data -> G2Lex assets -> Lexphon -> KokoroG2P
```

KokoroG2P should import the Python API, never spawn the Lexphon CLI in its normal runtime path.

Use `Phonemizer(..., fallback=None)` so unknown tokens remain explicit. For each token:

1. if Lexphon returned IPA, run the language/model-specific IPA-to-Kokoro converter;
2. if the IPA cannot be represented by the target Kokoro profile, apply KokoroG2P's existing fallback policy;
3. if Lexphon returned an unknown token, invoke KokoroG2P's eSpeak fallback and convert that IPA;
4. preserve Kokoro-specific ratings, stress controls, punctuation handling, and model vocabulary validation in KokoroG2P.

Lexphon's optional eSpeak fallback is intended for standalone CLI/library users, not as a replacement for application-specific fallback semantics.
