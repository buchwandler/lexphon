---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0003
release_version: v0.1.0
kind: changed
summary: Changed pronunciation asset handling to validate before atomic offline activation
status: accepted
audience: null
scopes: []
source_refs:
  - git:92b0bb1ae8dd71562cc0c4d5c9321841ef8cb0de
paths:
  - README.md
  - docs/ARCHITECTURE.md
  - lexphon/catalog.py
  - lexphon/cli.py
  - lexphon/engine.py
  - lexphon/store.py
  - tests/test_mvp.py
  - tests/test_production.py
issues: []
prs: []
sources:
  - git:92b0bb1ae8dd71562cc0c4d5c9321841ef8cb0de
contributors: []
breaking: false
internal: false
order: 3
---

Catalog and manifest identity, hashes, sizes, pronunciation encoding, and G2Lex readability are checked before installation. Production coverage verifies language layers, selectors, variants, structured CLI output, lifecycle operations, and failed-install cleanup.
