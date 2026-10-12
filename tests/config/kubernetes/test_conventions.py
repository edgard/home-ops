from pathlib import Path

import pytest

from tests.support.conventions import (
    assert_source_conventions,
    assert_manifest_source,
    assert_gateway,
)
from tests.support.sources import read_yaml
from tests.support.runtime import ROOT


def test_source_conventions():
    assert_source_conventions(ROOT)


@pytest.mark.parametrize(
    "doc",
    [
        {"kind": "ConfigMap", "apiVersion": "v1", "metadata": {"name": "demo"}},
        {"apiVersion": "v1", "kind": "ConfigMap", "data": {}, "metadata": {"name": "demo"}},
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "demo"},
            "status": {},
            "spec": {},
        },
        {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"annotations": {}, "name": "demo"}},
    ],
)
def test_owned_field_order(doc):
    with pytest.raises(AssertionError):
        assert_manifest_source(Path("apps/demo/demo/manifests/demo-config.configmap.yaml"), doc)


def test_gateway_relationship_accepts_moved_address_and_rejects_mismatch():
    base = ROOT / "apps/platform-system/istio/manifests"
    gateway = read_yaml(base / "istio-gateway.gateway.yaml")
    parameters = read_yaml(base / "istio-gateway-parameters.configmap.yaml")
    assert_gateway(gateway, parameters)
    gateway["metadata"]["annotations"]["external-dns.kubernetes.io/target"] = "192.0.2.10"
    with pytest.raises(AssertionError):
        assert_gateway(gateway, parameters)
    import json
    import yaml

    deployment = yaml.safe_load(parameters["data"]["deployment"])
    annotation = deployment["spec"]["template"]["metadata"]["annotations"]
    networks = json.loads(annotation["k8s.v1.cni.cncf.io/networks"])
    networks[0]["ips"] = ["192.0.2.10/24"]
    annotation["k8s.v1.cni.cncf.io/networks"] = json.dumps(networks)
    parameters["data"]["deployment"] = yaml.safe_dump(deployment)
    assert_gateway(gateway, parameters)


def test_owned_filename_and_optional_spec():
    doc = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "demo"}, "data": {}}
    assert_manifest_source(Path("apps/demo/demo/manifests/demo-config.configmap.yaml"), doc)
    with pytest.raises(AssertionError):
        assert_manifest_source(Path("apps/demo/demo/manifests/other.configmap.yaml"), doc)
    # The one checked-in upstream CRD bundle deliberately retains upstream ordering.
    assert_manifest_source(
        Path("apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml"),
        {"kind": "CustomResourceDefinition"},
    )


def test_duplicate_generated_application_names(tmp_path):
    for category in ["one", "two"]:
        app = tmp_path / "apps" / category / "same"
        app.mkdir(parents=True)
        (app / "app.yaml").write_text("chart: {}\n")
        (app / "values.yaml").write_text("{}\n")
    with pytest.raises(AssertionError, match="unique generated application"):
        assert_source_conventions(tmp_path)
