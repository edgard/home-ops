import hashlib
import importlib.util
import json
import sqlite3

import pytest

from tests.support.runtime import ROOT

BASE = ROOT / "ansible/roles/shared_data"


def adapter():
    spec = importlib.util.spec_from_file_location(
        "next_data_tools", BASE / "files/data_tools.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def generation(tmp_path):
    app = tmp_path / "source/selfhosted/demo"
    app.mkdir(parents=True)
    with sqlite3.connect(app / "source.db") as db:
        db.execute("CREATE TABLE evidence(id integer primary key)")
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "demo_key").write_text("K" * 64)
    registry = {
        "version": 1,
        "consumers": {
            "demo": {
                "namespace": "selfhosted",
                "enabled": False,
                "backend": "sqlite",
                "databases": [{"name": "demo", "owner": "demo"}],
                "roles": [
                    {
                        "name": "demo",
                        "password_key": "demo_password",
                        "connection_limit": 10,
                    }
                ],
                "workloads": [],
                "pvcs": ["selfhosted/demo"],
                "sqlite_files": ["selfhosted/demo/source.db"],
                "key_refs": ["demo_key"],
            }
        },
    }
    return tmp_path / "source", credentials, registry


def test_sqlite_capture_preserves_backend_and_verifies_retained_key(generation):
    root, credentials, registry = generation
    tools = adapter()
    manifest = tools.make_manifest(
        root,
        registry,
        ["demo"],
        "capture",
        {"demo": ["demo/image:1"]},
        credentials=credentials,
    )
    assert manifest["consumers"]["demo"]["backend"] == "sqlite"
    assert manifest["consumers"]["demo"]["databases"] == []
    assert manifest["consumers"]["demo"]["key_fingerprints"] == {
        "demo_key": hashlib.sha256(("K" * 64).encode()).hexdigest()
    }
    assert "K" * 64 not in json.dumps(manifest)
    tools.verify_manifest(
        root, manifest, registry=registry, apps=["demo"], credentials=credentials
    )
    (credentials / "demo_key").write_text("different-key")
    with pytest.raises(ValueError, match="key"):
        tools.verify_manifest(
            root, manifest, registry=registry, apps=["demo"], credentials=credentials
        )


def test_sqlite_capture_requires_registered_database_files(generation):
    root, credentials, registry = generation
    (root / "selfhosted/demo/source.db").unlink()
    tools = adapter()
    manifest = tools.make_manifest(
        root,
        registry,
        ["demo"],
        "capture",
        {"demo": ["demo/image:1"]},
        credentials=credentials,
    )
    with pytest.raises(ValueError):
        tools.verify_manifest(
            root, manifest, registry=registry, apps=["demo"], credentials=credentials
        )


def test_sqlite_capture_records_schema_and_native_version(generation):
    root, credentials, registry = generation
    manifest = adapter().make_manifest(
        root,
        registry,
        ["demo"],
        "capture",
        {"demo": ["demo/image:1"]},
        credentials=credentials,
    )
    schema = manifest["consumers"]["demo"]["schema_versions"][
        "selfhosted/demo/source.db"
    ]
    assert schema["client_version"].startswith("3.")
    assert isinstance(schema["user_version"], int)
    assert isinstance(schema["schema_version"], int)
    assert len(schema["schema_sha256"]) == 64
    manifest["consumers"]["demo"]["schema_versions"] = {}
    with pytest.raises(ValueError, match="schema"):
        adapter().verify_manifest(
            root, manifest, registry=registry, apps=["demo"], credentials=credentials
        )


def test_prepared_redis_allocation_is_not_captured_before_adoption(generation):
    import argparse

    root, credentials, registry = generation
    registry["consumers"]["demo"]["redis"] = {
        "database": 2,
        "username": "demo",
        "password_key": "demo_redis_password",
        "prefix": "demo:",
        "adopted": False,
    }
    tools = adapter()
    manifest = tools.make_manifest(
        root,
        registry,
        ["demo"],
        "capture",
        {"demo": ["demo/image:1"]},
        credentials=credentials,
    )
    assert manifest["consumers"]["demo"]["redis"] is None
    assert tools.estimate_capture(argparse.Namespace(apps=["demo"]), registry) == {
        "database_bytes": 0,
        "redis_bytes": 0,
    }
    tools.verify_manifest(
        root, manifest, registry=registry, apps=["demo"], credentials=credentials
    )
