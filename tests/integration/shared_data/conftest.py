import importlib.util
import sys

import pytest

from tests.support.runtime import ROOT

BASE = ROOT / "ansible/roles/shared_data"


@pytest.fixture
def adapters(monkeypatch):
    result = {}
    for name in ["data_tools", "capture", "upload", "recovery", "pending"]:
        spec = importlib.util.spec_from_file_location(
            name, BASE / "files" / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        result[name] = module
    return result


@pytest.fixture(scope="session")
def operations_image():
    from tests.support.data_generation import operations_image as selected_image

    return selected_image()
