---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: v0.2.2
kind: changed
summary:
  Changed catalog handling for kokoro-v1 assets and corrected LexHint defaults
  and regional compatibility
status: accepted
audience: null
scopes: []
source_refs:
  - git:a7f10d9d0730e024af2ac0779052d84f3bc990ed
paths:
  - .github/workflows/tests.yml
  - README.md
  - docs/ARCHITECTURE.md
  - docs/KOKOROG2P_INTEGRATION.md
  - docs/changelog.md
  - lexphon/catalog.py
  - lexphon/cli.py
  - lexphon/engine.py
  - lexphon/language.py
  - lexphon/profiles.toml
  - tests/fixtures/g2lex-v1-compat.g2lex
  - tests/fixtures/g2lex-v1-compat.jsonl
  - tests/test_mvp.py
  - tests/test_production.py
issues: []
prs: []
sources:
  - git:a7f10d9d0730e024af2ac0779052d84f3bc990ed
contributors: []
breaking: false
internal: false
order: 1
---
