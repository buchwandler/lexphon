---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: v0.2.3
kind: changed
summary: Changed package version reporting to use installed metadata and setuptools-scm
status: accepted
audience: null
scopes: []
source_refs:
  - git:25aeb7f370099a8b724a4bcf2cb77dc3e0745d18
paths:
  - .github/workflows/python-publish.yml
  - .github/workflows/tests.yml
  - lexphon/__init__.py
  - lexphon/_version.py
  - pyproject.toml
  - scripts/check_dist_versions.py
  - tests/test_version.py
issues: []
prs: []
sources:
  - git:25aeb7f370099a8b724a4bcf2cb77dc3e0745d18
contributors: []
breaking: false
internal: false
order: 1
---
