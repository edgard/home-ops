import copy
import hashlib
import json

import pytest

from tests.support.data_generation import schema_metadata
from tests.support.runtime import load_module


def tools():
    return load_module("shared_data/files/data_tools.py")


@pytest.fixture
def registry():
    return {
        "version": 1,
        "consumers": {
            "demo": {
                "namespace": "selfhosted",
                "enabled": True,
                "backend": "postgresql",
                "databases": [{"name": "demo", "owner": "demo"}],
                "roles": [
                    {
                        "name": "demo",
                        "password_key": "demo_db_password",
                        "connection_limit": 10,
                    }
                ],
                "redis": {
                    "database": 1,
                    "username": "demo",
                    "password_key": "demo_redis_password",
                    "prefix": "demo:",
                },
                "workloads": [{"kind": "Deployment", "name": "demo"}],
                "cronjobs": [],
                "pvcs": ["selfhosted/demo"],
                "key_refs": [],
            }
        },
    }


def test_registry_accepts_one_owner_for_two_databases(registry):
    registry["consumers"]["demo"]["databases"].append(
        {"name": "demo_log", "owner": "demo"}
    )
    assert (
        tools().validate_registry(registry)["consumers"]["demo"]["namespace"]
        == "selfhosted"
    )


@pytest.mark.parametrize(
    "field,value", [("database", 0), ("database", 16), ("prefix", "")]
)
def test_registry_rejects_unsafe_redis_allocation(registry, field, value):
    registry["consumers"]["demo"]["redis"][field] = value
    with pytest.raises(ValueError):
        tools().validate_registry(registry)


def test_registry_rejects_cross_app_shared_roles_and_redis(registry):
    registry["consumers"]["second"] = copy.deepcopy(registry["consumers"]["demo"])
    with pytest.raises(ValueError):
        tools().validate_registry(registry)


def test_registry_rejects_paths_outside_pvc_root(registry):
    registry["consumers"]["demo"]["pvcs"] = ["selfhosted/../postgresql"]
    with pytest.raises(ValueError):
        tools().validate_registry(registry)


def test_registry_checks_combined_connection_budget(registry):
    registry["consumers"]["demo"]["roles"][0]["connection_limit"] = 200
    with pytest.raises(ValueError):
        tools().validate_registry(registry)


@pytest.fixture
def complete_generation(tmp_path, registry):
    app = tmp_path / "selfhosted/demo"
    (app / ".home-ops/databases").mkdir(parents=True)
    (app / "file").write_bytes(b"payload")
    (app / ".home-ops/databases/demo.dump").write_bytes(b"dump")
    schema_metadata((app / ".home-ops/databases/demo.dump"))
    (tmp_path / ".home-ops").mkdir()
    (tmp_path / ".home-ops/redis.rdb").write_bytes(b"redis")
    manifest = tools().make_manifest(
        tmp_path, registry, ["demo"], "op", {"demo": ["example/demo:1"]}
    )
    return tmp_path, registry, manifest


@pytest.mark.parametrize(
    "change",
    [
        "missing_pvc",
        "unlisted_file",
        "unlisted_link",
        "omitted_file",
        "no_databases",
        "traversal",
    ],
)
def test_manifest_rejects_incomplete_or_uninventoried_generation(
    complete_generation, change
):
    root, registry, manifest = complete_generation
    app = root / "selfhosted/demo"
    if change == "missing_pvc":
        app.rename(root / "missing")
    elif change == "unlisted_file":
        (app / "new").write_bytes(b"unlisted")
    elif change == "unlisted_link":
        (app / "new").symlink_to("file")
    elif change == "omitted_file":
        manifest["files"].pop("selfhosted/demo/file")
    elif change == "no_databases":
        manifest["consumers"]["demo"]["databases"] = []
    elif change == "traversal":
        manifest["files"]["../outside"] = "a"
    with pytest.raises(ValueError):
        tools().verify_manifest(root, manifest)


def test_manifest_database_mapping_must_match_selected_registry(complete_generation):
    root, registry, manifest = complete_generation
    manifest["consumers"]["demo"]["databases"][0]["owner"] = "foreign"
    with pytest.raises(ValueError):
        tools().verify_manifest(root, manifest, registry=registry, apps=["demo"])


def test_manifest_verification_detects_partial_data_and_image_mismatch(
    tmp_path, registry
):
    app = tmp_path / "selfhosted/demo"
    app.mkdir(parents=True)
    (app / "file").write_bytes(b"payload")
    (app / ".home-ops/databases").mkdir(parents=True)
    (app / ".home-ops/databases/demo.dump").write_bytes(b"dump")
    schema_metadata((app / ".home-ops/databases/demo.dump"))
    (tmp_path / ".home-ops").mkdir()
    (tmp_path / ".home-ops/redis.rdb").write_bytes(b"redis")
    manifest = tools().make_manifest(
        tmp_path,
        registry,
        ["demo"],
        "test-operation",
        {"demo": ["example/demo@sha256:" + "a" * 64]},
    )
    tools().verify_manifest(tmp_path, manifest)
    with pytest.raises(ValueError, match="image"):
        tools().verify_manifest(
            tmp_path, manifest, {"demo": ["example/demo@sha256:" + "b" * 64]}
        )
    (app / "file").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        tools().verify_manifest(tmp_path, manifest)


def test_manifest_rejects_traversal_and_unknown_schema(tmp_path):
    for manifest in [
        {"version": 9},
        {"version": 1, "files": {"../outside": "a"}, "consumers": {}},
    ]:
        with pytest.raises(ValueError):
            tools().verify_manifest(tmp_path, manifest)


def test_manifest_rejects_missing_database_inventory(tmp_path):
    manifest = {
        "version": 1,
        "operation": "op",
        "files": {},
        "consumers": {
            "demo": {
                "backend": "postgresql",
                "databases": [{"name": "demo", "owner": "demo"}],
                "pvcs": ["selfhosted/demo"],
                "images": ["example/demo:1"],
                "key_refs": [],
            }
        },
    }
    with pytest.raises(ValueError, match="dump"):
        tools().verify_manifest(tmp_path, manifest)


def test_manifest_rejects_empty_consumer_generation(tmp_path):
    with pytest.raises(ValueError):
        tools().verify_manifest(tmp_path, {"version": 1, "consumers": {}, "files": {}})


def test_manifest_rejects_redis_generation_without_snapshot(tmp_path):
    manifest = {
        "version": 1,
        "operation": "op",
        "consumers": {
            "demo": {
                "backend": "postgresql",
                "databases": [{"name": "demo", "owner": "demo"}],
                "pvcs": ["selfhosted/demo"],
                "images": ["example/demo:1"],
                "redis": {"database": 1},
                "key_refs": [],
            }
        },
        "files": {"selfhosted/demo/.home-ops/databases/demo.dump": "a"},
    }
    with pytest.raises(ValueError, match="Redis"):
        tools().verify_manifest(tmp_path, manifest)


def test_pending_snapshot_cannot_be_promoted_after_partial_upload():
    for code in [1, 2, 3]:
        with pytest.raises(ValueError):
            tools().successful_snapshot(
                code, [{"message_type": "summary", "snapshot_id": "abc"}]
            )
    assert (
        tools().successful_snapshot(
            0, [{"message_type": "summary", "snapshot_id": "abc"}]
        )
        == "abc"
    )


def test_credentials_are_not_embedded_in_manifests(tmp_path, registry):
    (tmp_path / "selfhosted/demo").mkdir(parents=True)
    registry["consumers"]["demo"]["key_refs"] = ["demo_secret_key"]
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "demo_secret_key").write_text("retained-encryption-key")
    manifest = tools().make_manifest(
        tmp_path, registry, ["demo"], "op", {}, credentials=credentials
    )
    encoded = json.dumps(manifest)
    assert "retained-encryption-key" not in encoded
    assert (
        manifest["consumers"]["demo"]["key_fingerprints"]["demo_secret_key"]
        == hashlib.sha256(b"retained-encryption-key").hexdigest()
    )
    assert "demo_db_password" not in encoded
    assert manifest["consumers"]["demo"]["key_refs"] == ["demo_secret_key"]
