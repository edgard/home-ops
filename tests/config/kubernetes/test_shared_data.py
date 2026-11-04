"""Shared infrastructure must remain outside destructive app-file recovery."""

import hashlib

import yaml

from tests.support.runtime import ROOT
from tests.support.sources import read_yaml


def infrastructure_claims():
    claims = []
    for category, app in [
        ("platform-system", "postgresql"),
        ("platform-system", "redis"),
        ("selfhosted", "shared-data"),
    ]:
        for path in (ROOT / "apps" / category / app / "manifests").glob("*.yaml"):
            doc = read_yaml(path)
            if doc.get("kind") == "PersistentVolumeClaim":
                claims.append(
                    doc["metadata"]["namespace"] + "/" + doc["metadata"]["name"]
                )
    assert claims
    return claims


def test_shared_infrastructure_never_uses_generic_file_restore_or_live_capture():
    claims = infrastructure_claims()
    restore = read_yaml(ROOT / "ansible/roles/restic/defaults/main.yml")
    assert set(claims) <= set(restore["restic_restore_excluded_pvcs"])
    backup = read_yaml(ROOT / "apps/selfhosted/restic/values.yaml")["controllers"][
        "backup"
    ]["containers"]["app"]["args"]
    for claim in claims:
        assert "/data/appdata/" + claim in backup


def test_registry_delivery_and_secret_namespace_permission_agree():
    source = (ROOT / "ansible/roles/shared_data/files/registry.yaml").read_bytes()
    cm = read_yaml(
        ROOT
        / "apps/selfhosted/shared-data/manifests/shared-data-registry.configmap.yaml"
    )
    assert yaml.safe_load(cm["data"]["registry.yaml"]) == yaml.safe_load(source)
    assert (
        hashlib.sha256(cm["data"]["registry.yaml"].encode().rstrip(b"\n")).digest()
        == hashlib.sha256(source.rstrip(b"\n")).digest()
    )
    registry = yaml.safe_load(source)
    store = read_yaml(
        ROOT
        / "apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml"
    )
    allowed = set(store["spec"]["conditions"][0]["namespaces"])
    assert {app["namespace"] for app in registry["consumers"].values()} <= allowed
    pg = read_yaml(ROOT / "apps/platform-system/postgresql/values.yaml")
    settings = dict(
        value.split("=", 1)
        for value in pg["controllers"]["main"]["containers"]["app"]["args"]
        if "=" in value
    )
    budget = sum(
        role["connection_limit"]
        for app in registry["consumers"].values()
        for role in app.get("roles", [])
    )
    assert budget <= int(settings["max_connections"]) - 20


def test_prepared_schedulers_use_published_images_and_remain_suspended():
    values = read_yaml(ROOT / "apps/selfhosted/shared-data/values.yaml")
    for controller in values["controllers"].values():
        assert controller["cronjob"]["suspend"] is True
        for container in controller["containers"].values():
            image = container["image"]
            assert image["repository"] == "ghcr.io/edgard/home-ops-data-tools"
            assert len(image["tag"]) == 40 and image["digest"].startswith("sha256:")
    watchdog = values["controllers"]["watchdog"]
    assert watchdog["cronjob"]["concurrencyPolicy"] == "Forbid"


def test_operations_rbac_has_no_cluster_mutation_or_secret_listing():
    directory = ROOT / "apps/selfhosted/shared-data/manifests"
    project = read_yaml(ROOT / "argocd/projects/selfhosted.appproject.yaml")
    destinations = {item["namespace"] for item in project["spec"]["destinations"]}
    for path in directory.glob("*.yaml"):
        doc = read_yaml(path)
        if doc.get("kind") in {"Role", "RoleBinding"}:
            assert doc["metadata"]["namespace"] in destinations
        if doc.get("kind") == "ClusterRole":
            for rule in doc["rules"]:
                assert set(rule["verbs"]) <= {"get", "list", "watch"}
                assert not {"secrets", "persistentvolumeclaims"} & set(
                    rule["resources"]
                )


def test_database_volume_ownership_is_not_rewritten_by_kubelet():
    for name in ["postgresql", "redis"]:
        values = read_yaml(ROOT / f"apps/platform-system/{name}/values.yaml")
        security = values["defaultPodOptions"]["securityContext"]
        assert "fsGroup" not in security
        assert "fsGroupChangePolicy" not in security
