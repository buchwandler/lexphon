---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: v0.1.0
kind: added
summary:
  Added lexicon-first phonemization with layered lookup and normalized IPA
  output
status: accepted
audience: null
scopes: []
source_refs:
  - git:c8033ed831cb3fca1a33f4f505b47369cd6c0235
paths:
  - README.md
  - docs/ARCHITECTURE.md
  - docs/KOKOROG2P_INTEGRATION.md
  - examples/kokorog2p_backend.py
  - lexphon
  - pyproject.toml
  - tests/test_mvp.py
issues: []
prs: []
sources:
  - git:c8033ed831cb3fca1a33f4f505b47369cd6c0235
contributors: []
breaking: false
internal: false
order: 2
---

The Python API and CLI support language profiles, token-level provenance, pronunciation variants, explicit unknown-token handling, and optional eSpeak fallback. Integration guidance keeps downstream Kokoro conversion and fallback policy outside Lexphon.
