---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0004
release_version: v0.1.1
kind: added
summary: Added explicit CLI commands and structured diagnostics for unavailable pronunciation
  data
status: accepted
audience: null
scopes: []
source_refs:
- git:0a7701814f3c3d344306f60880982af54fbba8e2
paths:
- README.md
- docs/ARCHITECTURE.md
- lexphon/__init__.py
- lexphon/cli.py
- lexphon/errors.py
- lexphon/store.py
- tests/test_production.py
issues: []
prs: []
sources:
- git:0a7701814f3c3d344306f60880982af54fbba8e2
contributors: []
breaking: false
internal: false
order: 4
---
The CLI now documents and supports explicit phonemize, data, and language commands. Manifest and asset retrieval failures expose resource context through DataDownloadError and do not activate partial installations.
