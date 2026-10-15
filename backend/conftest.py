from collections.abc import Iterator

import pytest

from seaweedfs_support import SeaweedFs, run_seaweedfs


@pytest.fixture(scope="session")
def seaweedfs() -> Iterator[SeaweedFs]:
    with run_seaweedfs() as server:
        yield server
