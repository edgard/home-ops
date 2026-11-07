"""Keep cold authority faithful to an empty or explicitly supplied API state."""

import json
from pathlib import Path
from urllib.request import urlopen

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.integration.cold_bootstrap.support import extend_api


def service_accounts(connection):
    config = yaml.safe_load(Path(connection["kubeconfig_path"]).read_text())
    server = config["clusters"][0]["cluster"]["server"]
    with urlopen(
        server + "/api/v1/namespaces/selfhosted/serviceaccounts", timeout=5
    ) as response:
        return json.load(response)["items"]


@pytest.mark.parametrize("existing", [False, True])
def test_cold_api_preserves_only_explicit_service_accounts(
    tmp_path, monkeypatch, existing
):
    extend_api(monkeypatch)
    supplied = (
        [api.obj("ServiceAccount", "explicit-account", "selfhosted")]
        if existing
        else []
    )
    with api.maintenance_api(tmp_path, supplied) as (connection, _state):
        assert service_accounts(connection) == supplied


def test_ordinary_api_keeps_default_executor_service_account(tmp_path):
    with api.maintenance_api(tmp_path, []) as (connection, _state):
        accounts = service_accounts(connection)
        assert len(accounts) == 1
        assert accounts[0]["metadata"]["name"] == "shared-data"
