# KokoroG2P integration

The dependency direction is:

```text
g2lex-data -> G2Lex assets -> Lexphon -> KokoroG2P
```

KokoroG2P should import Lexphon's Python API. It should not spawn the CLI in its normal runtime path.

## Runtime contract

Install the desired Lexphon assets explicitly before starting an offline application:

```bash
lexphon data install de-de:gold
```

Use `Phonemizer(..., fallback=None)` so unknown tokens remain explicit. For each token:

1. If Lexphon returned IPA, convert it with the language and model-specific IPA-to-Kokoro converter.
2. If the IPA cannot be represented by the target profile, apply KokoroG2P's existing fallback policy.
3. If Lexphon returned an unknown token, invoke KokoroG2P's eSpeak fallback and convert that result.
4. Preserve Kokoro-specific ratings, stress controls, punctuation handling, and vocabulary validation in KokoroG2P.

Lexphon results are structured. Each token provides the original text, IPA pronunciation, source category, output alphabet, logical lexicon ID, matched key, source encoding, ordered IPA variants, selector tag, known status, and punctuation status. The first variant is primary, but later variants remain available to the application.

German supports `de` and `de-de` aliases, defaults to `de-de:gold`, and allows explicit `de-de:crane`, `de-de:espeak`, and `de-de:olaph` layers. English CMUdict is selected explicitly with `en-us:cmudict`; it does not replace the generic `en-us:gold` default.

Lexphon performs no catalog lookup or dictionary download during construction or phonemization. Its optional eSpeak fallback is a generic standalone feature and must not replace KokoroG2P's application-specific fallback semantics.

Lexphon does not import KokoroG2P, return Kokoro phonemes, validate the Kokoro inventory, apply model ratings, or decide model-specific stress and fallback behavior.
