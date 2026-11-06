import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.support.data_generation import schema_metadata
from tests.support.runtime import ROOT

BASE = ROOT / "ansible/roles/shared_data"


def recovery():
    return load_adapter("recovery")


def load_adapter(name):
    for dependency in {
        "capture": ["data_tools"],
        "recovery": ["data_tools", "capture"],
        "upload": ["data_tools"],
    }.get(name, []):
        sys.modules[dependency] = load_adapter(dependency)
    spec = importlib.util.spec_from_file_location(name, BASE / "files" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_selection_uses_canonical_tag_and_absolute_time():
    rows = [
        {
            "id": "a" * 64,
            "tags": ["appdata"],
            "paths": ["/data/appdata"],
            "hostname": "homelab",
            "time": "2026-11-04T11:30:00+02:00",
        },
        {
            "id": "b" * 64,
            "tags": ["appdata"],
            "paths": ["/data/appdata"],
            "hostname": "homelab",
            "time": "2026-11-04T10:00:00+00:00",
        },
        {
            "id": "c" * 64,
            "tags": ["appdata", "appdata-pending"],
            "paths": ["/data/appdata"],
            "hostname": "homelab",
            "time": "2026-11-05T10:00:00Z",
        },
    ]
    assert recovery().choose_snapshot(rows, "latest", "/data/appdata") == "b" * 64
    with pytest.raises(ValueError):
        recovery().choose_snapshot(rows, "c" * 8, "/data/appdata")
    with pytest.raises(ValueError):
        recovery().choose_snapshot(rows, "../../invalid", "/data/appdata")


def test_native_restic_stages_only_selected_application(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "repo"))
    monkeypatch.setenv("RESTIC_PASSWORD", "synthetic-only")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "appdata with spaces"
    registry = {"version": 1, "consumers": {}}
    for name in ["demo", "other"]:
        pvc = "selfhosted/" + name
        registry["consumers"][name] = {
            "enabled": True,
            "backend": "postgresql",
            "namespace": "selfhosted",
            "roles": [
                {
                    "name": name,
                    "password_key": name + "_password",
                    "connection_limit": 10,
                }
            ],
            "databases": [{"name": name, "owner": name}],
            "pvcs": [pvc],
            "workloads": [],
            "key_refs": [],
        }
        directory = root / pvc / ".home-ops/databases"
        directory.mkdir(parents=True)
        (directory / (name + ".dump")).write_bytes(b"synthetic dump")
        schema_metadata((directory / (name + ".dump")))
        (root / pvc / "file").write_text(name)
    registry["consumers"]["other"]["redis"] = {
        "database": 2,
        "username": "other",
        "password_key": "other_redis_password",
        "prefix": "other:",
    }
    (root / ".home-ops").mkdir()
    (root / ".home-ops/redis.rdb").write_bytes(b"synthetic redis")
    tools = load_adapter("data_tools")
    manifest = tools.make_manifest(
        root,
        registry,
        ["demo", "other"],
        "capture",
        {"demo": ["image/demo:1"], "other": ["image/other:1"]},
    )
    (root / ".home-ops/manifest.json").write_text(json.dumps(manifest))
    subprocess.run(["restic", "init"], check=True, capture_output=True)
    with patch.dict(sys.modules, {"data_tools": tools}):
        upload = load_adapter("upload")
    snapshot = upload.upload(
        "capture",
        manifest,
        root=str(root),
        manifest_sha256=__import__("hashlib")
        .sha256((root / ".home-ops/manifest.json").read_bytes())
        .hexdigest(),
    )
    args = argparse.Namespace(
        snapshot="latest",
        snapshot_root=str(root),
        staging=str(tmp_path / "stage"),
        operation="recover",
        apps=["demo"],
        images=json.dumps({"demo": ["image/demo:1"]}),
        credentials=tmp_path / "credentials",
    )
    result = recovery().stage(args, registry)
    assert result["snapshot"] == snapshot
    staged = Path(result["root"])
    assert (staged / "selfhosted/demo/file").read_text() == "demo"
    assert not (staged / "selfhosted/other").exists()
    assert not (staged / ".home-ops/redis.rdb").exists()
    recovery().validate(args, registry, {"demo": ["image/demo:1"]})
    (staged / "selfhosted/demo/file").write_text("changed")
    with pytest.raises(ValueError):
        recovery().validate(args, registry, {"demo": ["image/demo:1"]})
