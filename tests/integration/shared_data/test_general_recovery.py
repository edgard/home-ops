"""Real Restic selection and immutable staging boundaries for file recovery."""

import argparse
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import yaml

from tests.support.data_generation import operations_image
from tests.support.runtime import ROOT

HERE = ROOT / ".pytest_cache" / "general-restore"
ROLE = ROOT / "ansible/roles/shared_data"


def adapters():
    result = {}
    for name in ["data_tools", "capture", "upload", "recovery"]:
        spec = importlib.util.spec_from_file_location(
            name, ROLE / "files" / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        result[name] = module
    return result


def registry():
    return {
        "version": 1,
        "consumers": {
            "demo": {
                "enabled": True,
                "backend": "sqlite",
                "namespace": "selfhosted",
                "pvcs": ["selfhosted/demo"],
                "sqlite_files": ["selfhosted/demo/db.sqlite3"],
                "roles": [],
                "databases": [],
                "key_refs": [],
                "workloads": [],
            },
            "oldsqlite": {
                "enabled": False,
                "backend": "sqlite",
                "namespace": "media",
                "pvcs": ["media/oldsqlite"],
                "sqlite_files": ["media/oldsqlite/db.sqlite3"],
                "roles": [],
                "databases": [],
                "key_refs": [],
                "workloads": [],
            },
        },
        "file_consumers": {
            "files": {"namespace": "media", "pvcs": ["media/files"], "workloads": []}
        },
    }


def legacy_mapping():
    return {
        "files": {
            "namespace": "media",
            "pvcs": ["media/files"],
            "backend": "files",
            "sqlite_files": [],
            "mode": "live-files",
        },
        "oldsqlite": {
            "namespace": "media",
            "pvcs": ["media/oldsqlite"],
            "backend": "sqlite",
            "sqlite_files": ["media/oldsqlite/db.sqlite3"],
            "mode": "live-files",
        },
    }


def run(*command):
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    tmp_path = HERE / "runtime" / ("adapter-" + uuid.uuid4().hex)
    tmp_path.mkdir(parents=True, mode=0o700)
    for key, value in {
        "RESTIC_REPOSITORY": str(tmp_path / "repo"),
        "RESTIC_PASSWORD": "synthetic-only",
        "RESTIC_CACHE_DIR": str(tmp_path / "cache"),
    }.items():
        monkeypatch.setenv(key, value)
    root = tmp_path / "appdata"
    for relative in [
        "selfhosted/demo",
        "media/files",
        "media/oldsqlite",
        "selfhosted/unselected",
        "platform-system/postgresql",
    ]:
        directory = root / relative
        directory.mkdir(parents=True)
        (directory / "file").write_text(relative + "-original")
    for relative in ["selfhosted/demo", "media/oldsqlite"]:
        with sqlite3.connect(root / relative / "db.sqlite3") as connection:
            connection.execute("CREATE TABLE evidence(value text)")
            connection.execute("INSERT INTO evidence VALUES ('original')")
    run("restic", "init")
    tools = adapters()
    manifest = tools["data_tools"].make_manifest(
        root, registry(), ["demo"], "capture", {"demo": ["image/demo:1"]}
    )
    # Explicit fixture models modern snapshots even before capture supports the mapping.
    manifest["legacy_consumers"] = legacy_mapping()
    (root / ".home-ops").mkdir()
    manifest_file = root / ".home-ops/manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    def backup(
        *,
        tags=(
            "appdata-consumer-demo",
            "appdata-consumer-files",
            "appdata-consumer-oldsqlite",
        ),
    ):
        output = run(
            "restic",
            "backup",
            str(root),
            "--host",
            "homelab",
            "--tag",
            "appdata",
            *[value for tag in tags for value in ["--tag", tag]],
            "--json",
        )
        return [
            json.loads(row)["snapshot_id"]
            for row in output.splitlines()
            if json.loads(row).get("message_type") == "summary"
        ][0]

    args = argparse.Namespace(
        snapshot="latest",
        snapshot_root=str(root),
        staging=str(tmp_path / "stage"),
        operation="recover",
        apps=["files"],
        images="{}",
        credentials=tmp_path / "credentials",
    )
    try:
        yield tools, root, manifest, manifest_file, backup, args
    finally:
        shutil.rmtree(tmp_path)


def test_capture_records_registered_live_file_mapping_without_image_claims(snapshot):
    tools, root, *_ = snapshot
    manifest = tools["data_tools"].make_manifest(
        root, registry(), ["demo"], "capture", {"demo": ["image/demo:1"]}
    )
    assert manifest["legacy_consumers"] == legacy_mapping()


def test_modern_selected_legacy_stages_only_selected_file_payload(snapshot):
    tools, root, manifest, manifest_file, backup, args = snapshot
    selected = backup()
    metadata = tools["recovery"].stage(args, registry())
    assert metadata["snapshot"] == selected
    assert (
        metadata["manifest_sha256"]
        == hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    )
    assert len(metadata["selection_sha256"]) == 64
    staged = Path(metadata["root"])
    assert (staged / "media/files/file").read_text() == "media/files-original"
    assert not (staged / "selfhosted/demo").exists()
    assert not (staged / "selfhosted/unselected").exists()
    assert not (staged / "platform-system/postgresql").exists()
    tools["recovery"].validate(args, registry())


@pytest.mark.parametrize("change", ["mapping", "payload", "metadata", "sqlite"])
def test_legacy_mutation_refused_before_any_live_write(snapshot, change):
    tools, root, manifest, manifest_file, backup, args = snapshot
    args.apps = ["oldsqlite"]
    backup()
    metadata = tools["recovery"].stage(args, registry())
    args.manifest_sha256 = metadata["manifest_sha256"]
    args.selection_sha256 = metadata["selection_sha256"]
    args.live_root = str(root.parent / "live")
    expected = registry()
    if change == "mapping":
        expected["consumers"]["oldsqlite"]["pvcs"] = ["media/elsewhere"]
        expected["consumers"]["oldsqlite"]["sqlite_files"] = [
            "media/elsewhere/db.sqlite3"
        ]
    elif change == "payload":
        (Path(metadata["root"]) / "media/oldsqlite/file").write_text("corrupt")
    elif change == "sqlite":
        (Path(metadata["root"]) / "media/oldsqlite/db.sqlite3").write_text(
            "not a SQLite database"
        )
    else:
        metadata_file = Path(args.staging) / "restores/recover/recovery.json"
        altered = json.loads(metadata_file.read_text())
        altered["snapshot"] = "f" * 64
        altered["selection_sha256"] = hashlib.sha256(
            json.dumps(
                {k: v for k, v in altered.items() if k != "selection_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        metadata_file.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        tools["recovery"].restore_files(args, expected)
    assert not Path(args.live_root).exists()


def test_legacy_sqlite_quick_check_required_even_if_restic_integrity_is_valid(snapshot):
    tools, root, manifest, manifest_file, backup, args = snapshot
    args.apps = ["oldsqlite"]
    (root / "media/oldsqlite/db.sqlite3").write_text("not a SQLite database")
    backup()
    with pytest.raises(ValueError):
        tools["recovery"].stage(args, registry())


@pytest.mark.parametrize("modern", [False, True])
def test_partial_latest_does_not_hide_snapshot_covering_all_requested(snapshot, modern):
    tools, root, manifest, manifest_file, backup, args = snapshot
    args.apps = ["files", "oldsqlite"]
    if not modern:
        manifest_file.unlink()
    complete = backup(
        tags=()
        if not modern
        else ("appdata-consumer-files", "appdata-consumer-oldsqlite")
    )
    backup(tags=("appdata-consumer-files",))
    result = tools["recovery"].stage(args, registry())
    assert result["snapshot"] == complete


def test_manifestless_file_selection_allowed_but_expected_postgres_rejected(snapshot):
    tools, root, manifest, manifest_file, backup, args = snapshot
    manifest_file.unlink()
    selected = backup(tags=())
    args.snapshot = selected[:12]
    result = tools["recovery"].stage(args, registry())
    assert result["snapshot"] == selected
    assert result["manifest_sha256"] is None
    assert result["compatibility"] == "historical-live-files"
    args.operation = "pg-recover"
    args.apps = ["demo"]
    expected = registry()
    expected["consumers"]["demo"].update(
        backend="postgresql",
        sqlite_files=[],
        roles=[
            {"name": "demo", "password_key": "demo_password", "connection_limit": 10}
        ],
        databases=[{"name": "demo", "owner": "demo"}],
    )
    with pytest.raises(ValueError, match="manifest"):
        tools["recovery"].stage(args, expected)


@pytest.mark.parametrize(
    "bad", ["missing", "corrupt", "incompatible", "null", "untagged-null"]
)
def test_modern_manifests_cannot_fall_back_to_historical_files(snapshot, bad):
    tools, root, manifest, manifest_file, backup, args = snapshot
    if bad == "missing":
        manifest_file.unlink()
    elif bad == "corrupt":
        manifest_file.write_text("{invalid json")
    elif bad in {"null", "untagged-null"}:
        manifest_file.write_text("null\n")
    else:
        manifest["legacy_consumers"]["files"]["pvcs"] = ["media/wrong"]
        manifest_file.write_text(json.dumps(manifest))
    backup(tags=() if bad == "untagged-null" else ("appdata-consumer-files",))
    with pytest.raises(ValueError):
        tools["recovery"].stage(args, registry())
    assert not (Path(args.staging) / "restores/recover/recovery.json").exists()


@pytest.mark.parametrize("action", ["validate", "files", "postgres", "redis"])
def test_null_manifest_rejected_by_revalidation_and_destructive_entrypoints(
    snapshot, action
):
    tools, root, manifest, manifest_file, backup, args = snapshot
    raw = b"null\n"
    manifest_file.write_bytes(raw)
    selected = backup(tags=("appdata-consumer-files",))
    operation = Path(args.staging) / "restores/recover"
    run(
        "restic",
        "restore",
        selected,
        "--target",
        str(operation),
        "--include",
        str(root / "media/files"),
        "--include",
        str(manifest_file),
    )
    # Model an already-bound selection from the pre-fix coordinator.  The
    # receiving adapter must reject null again before any live replacement.
    metadata = {
        "operation": args.operation,
        "snapshot": selected,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "root": str(operation / str(root).lstrip("/")),
        "apps": ["files"],
        "compatibility": "modern-manifest",
        "legacy_consumers": {"files": legacy_mapping()["files"]},
        "legacy_inventory_sha256": hashlib.sha256(
            json.dumps(
                {
                    "media/files": {
                        "file": [
                            "file",
                            hashlib.sha256(b"media/files-original").hexdigest(),
                        ]
                    }
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
    }
    metadata["selection_sha256"] = hashlib.sha256(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    (operation / "recovery.json").write_text(json.dumps(metadata))
    registry_file = root.parent / "registry.yaml"
    registry_file.write_text(yaml.safe_dump(registry()))
    live = root.parent / "live"
    marker = live / "media/files/file"
    marker.parent.mkdir(parents=True)
    marker.write_text("untouched-live")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            "-v",
            str(root.parent) + ":" + str(root.parent),
            "-v",
            str(ROLE) + ":" + str(ROLE) + ":ro",
            operations_image(),
            str(ROLE / "files/recovery.py"),
            action,
            "--registry",
            str(registry_file),
            "--apps",
            "files",
            "--operation",
            args.operation,
            "--staging",
            args.staging,
            "--snapshot-root",
            str(root),
            "--live-root",
            str(live),
            "--images",
            "{}",
            "--manifest-sha256",
            metadata["manifest_sha256"],
            "--selection-sha256",
            metadata["selection_sha256"],
            "--confirm",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert json.loads(result.stderr)["error_type"] == "ValueError"
    assert marker.read_text() == "untouched-live"


def test_upload_requires_captured_legacy_mapping_before_creating_snapshot(snapshot):
    tools, root, manifest, manifest_file, backup, args = snapshot
    manifest["legacy_consumers"]["files"]["pvcs"] = ["media/other"]
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        tools["upload"].upload(
            "capture",
            manifest,
            root=str(root),
            manifest_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
            registry=registry(),
            apps=["demo"],
            legacy_pvcs=["media/files", "media/oldsqlite"],
        )
    assert json.loads(run("restic", "snapshots", "--json")) == []


@pytest.mark.parametrize("modern", [False, True])
def test_legacy_symlink_cannot_escape_selected_registered_pvc(snapshot, modern):
    tools, root, manifest, manifest_file, backup, args = snapshot
    (root / "media/files/redirect").symlink_to("../../selfhosted/unselected/file")
    if not modern:
        manifest_file.unlink()
    backup(tags=() if not modern else ("appdata-consumer-files",))
    with pytest.raises(ValueError, match="symlink"):
        tools["recovery"].stage(args, registry())


def test_combined_redis_scope_skips_files_and_unadopted_allocations():
    spec = importlib.util.spec_from_file_location(
        "data_filters", ROLE / "filter_plugins/data.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = registry()
    data["consumers"]["demo"]["redis"] = {"database": 1, "adopted": True}
    data["consumers"]["oldsqlite"]["redis"] = {"database": 2, "adopted": False}
    assert module.redis_apps(data, ["files", "demo", "oldsqlite"]) == ["demo"]
