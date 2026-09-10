# Pronunciation benchmarks

Each module in `lexicons/` declares one production pronunciation asset and delegates execution to the shared runner. The catalog is the inventory source, while demo and membership artifacts are excluded from quality benchmarking.

## Running benchmarks

Run one benchmark:

```bash
python -m benchmarks.pronunciation_validation.lexicons.benchmark_de_de_crane
```

Progress is enabled by default. It is written to stderr, flushed immediately, and reports the active benchmark, stage, and bounded counters. Use `--quiet` to suppress transient progress output. The final benchmark result and matrix index message remain on stdout.

The default word-list limit is 50,000 words. A language filter may select multiple lexicons:

```bash
python -m benchmarks.pronunciation_validation.run_all --language de-DE
```

Run exactly one benchmark with a smaller quick smoke list:

```bash
python -m benchmarks.pronunciation_validation.run_all \
  --lexicon de-de:crane \
  --limit 1000
```

The German matrix can also be smoke-tested with:

```bash
python -m benchmarks.pronunciation_validation.run_all \
  --language de-DE \
  --limit 1000
```

Use `--offline` to avoid network provisioning. Offline runs require cached word lists and lexicon assets.

## Catalog maintenance

Check catalog drift and create missing declarative modules:

```bash
python -m benchmarks.pronunciation_validation.sync_catalog --check
python -m benchmarks.pronunciation_validation.sync_catalog --write
```

Generated word lists, reports, and provisioned lexicons are kept under this package and are ignored by Git. The benchmark always constructs Lexphon with an explicit lexicon and `fallback=None`, so normal runtime lookup remains local and download-free. Assets using `kokoro-v1` are reported as `unsupported_encoding`; their bytes are not interpreted as IPA.

Word-list sources are curated in `wordlists.py`. Source URLs, revisions, formats, licensing notes, retrieval timestamps, and downloaded/adapted SHA-256 hashes are included in reports. The initial reference registry enables eSpeak and records when an eSpeak-derived lexicon uses the same source family.

## Phonodist validation

Install benchmark dependencies in a checkout with:

```bash
python -m pip install -e ".[dev]"
```

For an installed package, use the optional validation dependency:

```bash
python -m pip install "lexphon[validation]"
```

Phonodist is a second evidence channel. Legacy exact and broad distances and their classification remain unchanged. The benchmark records these Phonodist states:

- `active`: the dependency and the artifact language profile are available.
- `profile_unavailable`: Phonodist is installed, but no bundled language profile exists.
- `dependency_unavailable`: Phonodist is not installed.

The current Phonodist 0.1 profile is `de-DE`. Other language benchmarks continue to emit their existing local metrics unless Phonodist is available with a matching profile. Profile selection uses the lexicon artifact language, while Phonodist performs locale normalization.

Require the profile for a German matrix run with:

```bash
python -m benchmarks.pronunciation_validation.run_all \
  --language de-DE \
  --require-phonodist
```

Bulk Phonodist scoring uses score-only mode. Explanations are collected only for legacy mismatch rows and selector disagreements. Review `selector_disagreements.csv` and compare the independent metric rankings before considering any threshold calibration.

The reviewed calibration fixture is `fixtures/de_phonodist_calibration.tsv`. It records IPA pairs, expected relations, reasons, origins, and notes. It is evidence for later policy decisions, not a Phonodist classification threshold.
