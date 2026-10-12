from urllib.parse import urlsplit

import yaml

from tests.support.resources import assert_resource, assert_route_coverage
from tests.support.sources import read_yaml


def test_rendered_resources(rendered):
    for doc in rendered:
        try:
            assert_resource(doc)
        except AssertionError as error:
            raise AssertionError(
                f"{doc.get('kind')}/{doc.get('metadata', {}).get('name')}: {error}"
            ) from error


def test_route_coverage(repo_root, rendered):
    raw = [
        doc
        for path in (repo_root / "apps").glob("*/*/manifests/*.yaml")
        for doc in read_yaml(path, multiple=True)
    ]
    routes = {
        host
        for doc in rendered + raw
        if doc.get("kind") == "HTTPRoute"
        for host in doc["spec"]["hostnames"]
    }
    configmaps = [
        doc
        for doc in rendered
        if doc.get("kind") == "ConfigMap"
        and "config.yaml" in doc.get("data", {})
        and "gatus" in doc["metadata"]["name"]
    ]
    assert len(configmaps) == 1
    config = yaml.safe_load(configmaps[0]["data"]["config.yaml"])
    actual = [
        urlsplit(endpoint["url"]).hostname
        for endpoint in config["endpoints"]
        if endpoint.get("url", "").startswith(("https://", "http://"))
    ]
    assert_route_coverage(
        sorted(routes),
        read_yaml(repo_root / "apps/platform-system/gatus/values.yaml")["gateway"]["route"][
            "hosts"
        ],
        actual,
    )
