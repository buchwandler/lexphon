from __future__ import annotations

import lexphon


def test_package_version_is_available() -> None:
    assert isinstance(lexphon.__version__, str)
    assert lexphon.__version__
