# Pronunciation benchmarks

Each module in `lexicons/` declares one production pronunciation asset and delegates execution to the shared runner. The catalog is the inventory source, while demo and membership artifacts are excluded from quality benchmarking.

Run one benchmark:

```bash
python -m benchmarks.pronunciation_validation.lexicons.benchmark_de_de_crane
```

Run a matrix or an offline rerun:

```bash
python -m benchmarks.pronunciation_validation.run_all --language de-DE
python -m benchmarks.pronunciation_validation.run_all --offline
```

Check catalog drift and create missing declarative modules:

```bash
python -m benchmarks.pronunciation_validation.sync_catalog --check
python -m benchmarks.pronunciation_validation.sync_catalog --write
```

Generated word lists, reports, and provisioned lexicons are kept under this package and are ignored by Git. The benchmark always constructs Lexphon with an explicit lexicon and `fallback=None`, so normal runtime lookup remains local and download-free. Assets using `kokoro-v1` are reported as `unsupported_encoding`; their bytes are not interpreted as IPA.

Word-list sources are curated in `wordlists.py`. Source URLs, revisions, formats, licensing notes, retrieval timestamps, and downloaded/adapted SHA-256 hashes are included in reports. The initial reference registry enables eSpeak and records when an eSpeak-derived lexicon uses the same source family.
