---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 4
entry_id: entry-0001
release_version: v0.1.3
kind: fixed
summary:
  Fixed IPA marker normalization, structured provenance, and exact/prefix lookup
  parity
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0007
  - git:8de932526285cc59d31047758a009fe45015baf8
paths:
  - lexphon/alphabets.py
  - lexphon/engine.py
  - lexphon/models.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

Raw selected source pronunciations remain inspectable, and recognized language controls are represented as structured metadata for downstream consumers.
