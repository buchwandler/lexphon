---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0005
release_version: v0.1.1
kind: added
summary: Added prefix matching and six additional language profiles
status: accepted
audience: null
scopes: []
source_refs:
- git:3f935b71a215f16d78f6aa35be3621452048cdce
paths:
- lexphon/engine.py
- lexphon/profiles.toml
- tests/test_mvp.py
issues: []
prs: []
sources:
- git:3f935b71a215f16d78f6aa35be3621452048cdce
contributors: []
breaking: false
internal: false
order: 5
---
Phonemizer prefix lookup preserves layer precedence and longest-match ordering. Built-in profiles now include Russian, Thai, Vietnamese, Japanese, Korean, and Portuguese aliases.
