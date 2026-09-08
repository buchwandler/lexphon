from __future__ import annotations

import lexphon
import lexphon._version as version


def test_package_version_is_explicit_and_consistent() -> None:
    assert version.__version__ == "0.2.0"
    assert lexphon.__version__ == version.__version__
