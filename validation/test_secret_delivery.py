from datetime import datetime, timezone

import pytest


@pytest.fixture
def delivery(module_loader):
    return module_loader("cli_secrets/filter_plugins/secret_delivery.py")


def test_root_requires_every_source_revision_and_sync(delivery):
    root = {
        "spec": {"sources": [{}, {}]},
        "status": {"sync": {"status": "Synced", "revisions": ["new", "new"]}},
    }
    assert delivery.platform_root_ready(root, "new")
    root["status"]["sync"]["revisions"][1] = "old"
    assert not delivery.platform_root_ready(root, "new")
    root["status"]["sync"]["revisions"] = ["new"]
    assert not delivery.platform_root_ready(root, "new")
    root["status"]["sync"]["revisions"] = ["new", "new"]
    root["status"]["sync"]["status"] = "OutOfSync"
    assert not delivery.platform_root_ready(root, "new")


def test_ready_requires_fresh_valid_timestamp(delivery):
    now = datetime.now(timezone.utc)
    resource = {
        "status": {
            "refreshTime": "2000-01-01T00:00:00Z",
            "conditions": [{"type": "Ready", "status": "True"}],
        }
    }
    assert not delivery.platform_secret_ready(resource, now.timestamp())
    resource["status"]["refreshTime"] = now.isoformat()
    assert delivery.platform_secret_ready(resource, now.timestamp())
    resource["status"]["refreshTime"] = "invalid"
    assert not delivery.platform_secret_ready(resource, now.timestamp())
    resource["status"]["refreshTime"] = now.isoformat()
    resource["status"]["conditions"][0]["status"] = "False"
    assert not delivery.platform_secret_ready(resource, now.timestamp())


def test_provider_json_parser_never_surfaces_malformed_payload(delivery):
    assert delivery.safe_from_json("PRIVATE_PROVIDER_DIAGNOSTIC") is None
    assert delivery.safe_from_json('[{"id":"fixture"}]') == [{"id": "fixture"}]


def test_only_children_owned_by_expected_appset_count(delivery):
    resources = [
        {"metadata": {"name": "child", "ownerReferences": [{"uid": "expected"}]}},
        {"metadata": {"name": "unrelated", "ownerReferences": [{"uid": "other"}]}},
    ]
    assert delivery.platform_owned_applications(resources, "expected") == ["child"]
