import argparse
import hashlib
import json
import time

import pytest

from tests.support.data_generation import schema_metadata


def registry():
    return {
        "version": 1,
        "consumers": {
            "demo": {
                "namespace": "selfhosted",
                "enabled": True,
                "backend": "postgresql",
                "roles": [
                    {
                        "name": "demo",
                        "password_key": "demo_password",
                        "connection_limit": 10,
                    }
                ],
                "databases": [{"name": "demo", "owner": "demo"}],
                "pvcs": ["selfhosted/demo"],
                "workloads": [],
                "key_refs": [],
            }
        },
    }


def generation(tmp_path, tools):
    root = tmp_path / "generation"
    dump = root / "selfhosted/demo/.home-ops/databases/demo.dump"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"database-payload")
    schema_metadata(dump)
    (root / ".home-ops").mkdir()
    manifest = tools.make_manifest(
        root, registry(), ["demo"], "op", {"demo": ["image:1"]}
    )
    raw = json.dumps(manifest).encode()
    (root / ".home-ops/manifest.json").write_bytes(raw)
    return root, manifest, hashlib.sha256(raw).hexdigest()


def test_expired_deadline_starts_no_process(adapters, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("HOME_OPS_DATA_DEADLINE", str(time.time() - 1))
    monkeypatch.setattr(
        adapters["data_tools"].subprocess, "run", lambda *a, **k: calls.append(a)
    )
    with pytest.raises(TimeoutError):
        adapters["data_tools"].native(["should-not-start"])
    assert not calls
    root = tmp_path / "root/selfhosted/demo"
    root.mkdir(parents=True)
    with pytest.raises(TimeoutError):
        adapters["capture"].copy_files(
            tmp_path / "root",
            tmp_path / "destination",
            ["selfhosted/demo"],
            time.time() - 1,
        )
    assert not calls


def test_size_includes_sql_and_rdb_and_two_generations(adapters, tmp_path):
    app = tmp_path / "selfhosted/demo"
    app.mkdir(parents=True)
    (app / "data").write_bytes(b"x" * 100)
    assert (
        adapters["capture"].required_bytes(
            tmp_path, ["selfhosted/demo"], database_bytes=200, redis_bytes=200
        )
        == 1200
    )


def test_upload_rejects_wrong_canonical_mount_before_backup(adapters, tmp_path):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    canonical = tmp_path / "canonical"
    import shutil

    shutil.copytree(root, canonical)
    (canonical / "selfhosted/demo/.home-ops/databases/demo.dump").write_bytes(
        b"live-data"
    )
    schema_metadata((canonical / "selfhosted/demo/.home-ops/databases/demo.dump"))
    calls = []
    with pytest.raises(ValueError):
        adapters["upload"].upload(
            "op",
            manifest,
            run=lambda cmd: calls.append(cmd),
            root=str(canonical),
            generation_root=root,
            manifest_sha256=sha,
        )
    assert calls == []


def test_recovery_refuses_keys_without_current_mounted_credentials(adapters, tmp_path):
    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    manifest["consumers"]["demo"]["key_refs"] = ["demo_key"]
    manifest["consumers"]["demo"]["key_fingerprints"] = {"demo_key": "a" * 64}
    with pytest.raises(ValueError, match="key|credential"):
        adapters["data_tools"].verify_manifest(root, manifest)


def test_sqlite_never_restores_intended_postgres(adapters, tmp_path, monkeypatch):
    data = registry()
    data["consumers"]["demo"]["backend"] = "sqlite"
    calls = []
    monkeypatch.setattr(
        adapters["data_tools"], "connect_pg", lambda *a, **k: calls.append(a)
    )
    adapters["data_tools"].restore_postgres(
        argparse.Namespace(root=str(tmp_path), apps=["demo"]), data
    )
    assert not calls


def test_manifest_rejects_paths_outside_selected_pvcs(adapters, tmp_path):
    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    foreign = root / "selfhosted/other/private"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(b"private")
    manifest["files"]["selfhosted/other/private"] = hashlib.sha256(
        b"private"
    ).hexdigest()
    with pytest.raises(ValueError):
        adapters["data_tools"].verify_manifest(root, manifest)


def test_selected_manifest_is_immutable_and_excludes_foreign_redis(adapters):
    data = registry()
    manifest = {
        "version": 1,
        "consumers": {
            "demo": {
                "backend": "postgresql",
                "databases": [{"name": "demo", "owner": "demo"}],
                "pvcs": ["selfhosted/demo"],
                "redis": None,
            },
            "other": {},
        },
        "files": {
            "selfhosted/demo/.home-ops/databases/demo.dump": "d",
            "selfhosted/demo/file": "x",
            "selfhosted/other/file": "y",
            ".home-ops/redis.rdb": "z",
        },
        "symlinks": {},
    }
    before = json.dumps(manifest, sort_keys=True)
    selected = adapters["recovery"].selected_manifest(manifest, data, ["demo"])
    assert set(selected["files"]) == {
        "selfhosted/demo/file",
        "selfhosted/demo/.home-ops/databases/demo.dump",
    }
    assert json.dumps(manifest, sort_keys=True) == before


def test_sqlite_integrity_checked_even_when_hash_matches(adapters, tmp_path):
    data = registry()
    data["consumers"]["demo"].update(
        backend="sqlite", sqlite_files=["selfhosted/demo/source.db"]
    )
    app = tmp_path / "selfhosted/demo"
    app.mkdir(parents=True)
    (app / "source.db").write_bytes(b"not-a-sqlite-database")
    with pytest.raises(ValueError, match="SQLite"):
        adapters["data_tools"].make_manifest(
            tmp_path, data, ["demo"], "capture", {"demo": ["image:1"]}
        )


def test_publish_returns_manifest_digest_and_rejects_existing_generation(
    adapters, tmp_path
):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    published = tmp_path / "generations/op"
    assert (
        adapters["capture"].publish(root, published, registry=registry(), apps=["demo"])
        == sha
    )
    with pytest.raises(ValueError):
        adapters["capture"].publish(
            published, published, registry=registry(), apps=["demo"]
        )


def test_recovery_rejects_postgres_database_mapping_and_images(adapters, tmp_path):
    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    manifest["consumers"]["demo"]["databases"] = []
    with pytest.raises(ValueError, match="compatible|database"):
        adapters["recovery"].selected_manifest(manifest, registry(), ["demo"])
    _, manifest, _ = generation(tmp_path / "second", adapters["data_tools"])
    with pytest.raises(ValueError, match="image"):
        adapters["data_tools"].verify_manifest(
            root.parent / "second/generation",
            manifest,
            {"demo": ["image:2"]},
            registry=registry(),
            apps=["demo"],
        )


def test_copy_rejects_symlinked_destination_pvc(adapters, tmp_path):
    source = tmp_path / "source/selfhosted/demo"
    source.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = tmp_path / "destination"
    (destination / "selfhosted").mkdir(parents=True)
    (destination / "selfhosted/demo").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="destination|redirect"):
        adapters["capture"].copy_files(
            tmp_path / "source", destination, ["selfhosted/demo"], time.time() - 1
        )


def test_prune_preserves_pending_active_and_two_completed(adapters, tmp_path):
    completed = tmp_path / "uploaded"
    completed.mkdir()
    active = tmp_path / "uploads"
    active.mkdir()
    for index in range(6):
        root, _, sha = generation(tmp_path / str(index), adapters["data_tools"])
        target = tmp_path / "generations" / str(index)
        target.parent.mkdir(exist_ok=True)
        root.rename(target)
        if index < 5:
            (completed / (str(index) + ".json")).write_text(
                json.dumps({"manifest_sha256": sha, "snapshot": "a" * 64})
            )
        if index == 0:
            (active / "0.json").write_text("{}")
    adapters["capture"].prune_generations(tmp_path / "generations")
    assert {path.name for path in (tmp_path / "generations").iterdir()} == {
        "0",
        "3",
        "4",
        "5",
    }


@pytest.mark.parametrize(
    "pvc",
    [
        "platform-system/postgresql",
        "platform-system/redis",
        "selfhosted/shared-data-staging",
    ],
)
def test_registry_rejects_raw_engines_and_staging_as_appdata(adapters, pvc):
    data = registry()
    data["consumers"]["demo"]["pvcs"] = [pvc]
    with pytest.raises(ValueError, match="raw|staging|reserved"):
        adapters["data_tools"].validate_registry(data)


def test_sqlite_wal_verification_preserves_immutable_generation(adapters, tmp_path):
    import shutil
    import sqlite3

    data = registry()
    data["consumers"]["demo"].update(
        backend="sqlite", sqlite_files=["selfhosted/demo/source.db"]
    )
    original = tmp_path / "original.db"
    source = tmp_path / "generation/selfhosted/demo"
    source.mkdir(parents=True)
    with sqlite3.connect(original) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE evidence(value text)")
        db.execute("INSERT INTO evidence VALUES ('in-wal')")
        db.commit()
        for ending in ["", "-wal", "-shm"]:
            shutil.copyfile(str(original) + ending, source / ("source.db" + ending))
    root = tmp_path / "generation"
    manifest = adapters["data_tools"].make_manifest(
        root, data, ["demo"], "op", {"demo": ["image:1"]}
    )
    adapters["data_tools"].verify_manifest(root, manifest, registry=data, apps=["demo"])
    assert {
        path: adapters["data_tools"].digest(root / path) for path in manifest["files"]
    } == manifest["files"]
