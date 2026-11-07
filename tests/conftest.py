import os

import pytest

from tests.support.runtime import ROOT, load_module


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart():
    # Fixture repositories must never inherit another repository's Git context.
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            del os.environ[name]


@pytest.fixture(scope="session")
def repo_root():
    return ROOT


@pytest.fixture
def module_loader():
    return load_module
