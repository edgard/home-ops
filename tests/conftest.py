import pytest

from tests.support.runtime import ROOT, load_module


@pytest.fixture(scope="session")
def repo_root():
    return ROOT


@pytest.fixture
def module_loader():
    return load_module
