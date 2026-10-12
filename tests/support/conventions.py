"""Small source conventions that native syntax/schema tools do not check."""

import ipaddress
import json

import yaml

from tests.support.applications import ordered
from tests.support.sources import applications, manifest_paths, read_yaml

VENDORED = "apps/platform-system/gateway-api/manifests/gateway-api-crds.yaml"


def assert_manifest_source(relative, doc):
    if str(relative) == VENDORED:
        return
    keys = list(doc)
    assert keys[:3] == ["apiVersion", "kind", "metadata"], f"resource field order: {relative}"
    assert "spec" not in keys or keys[3] == "spec", f"spec field order: {relative}"
    ordered(doc["metadata"], ["name", "namespace", "labels", "annotations"])
    if relative.parts[0] == "apps":
        assert relative.name.startswith(
            relative.parts[2] + "-"
        ), f"owned manifest filename: {relative}"
    else:
        assert "." in relative.name, f"resource filename: {relative}"


def assert_gateway(gateway, parameters):
    target = gateway["metadata"]["annotations"]["external-dns.kubernetes.io/target"]
    deployment = yaml.safe_load(parameters["data"]["deployment"])
    networks = json.loads(
        deployment["spec"]["template"]["metadata"]["annotations"]["k8s.v1.cni.cncf.io/networks"]
    )
    addresses = [
        str(ipaddress.ip_interface(cidr).ip)
        for network in networks
        for cidr in network.get("ips", [])
    ]
    assert target in addresses, "gateway DNS target must match Multus address"


def assert_source_conventions(root):
    apps = applications(root)
    names = [app.name for app in apps]
    assert len(names) == len(set(names)), "unique generated application names"
    for path in manifest_paths(root):
        for doc in read_yaml(path, multiple=True):
            assert_manifest_source(path.relative_to(root), doc)
    istio = root / "apps/platform-system/istio/manifests"
    assert_gateway(
        read_yaml(istio / "istio-gateway.gateway.yaml"),
        read_yaml(istio / "istio-gateway-parameters.configmap.yaml"),
    )
