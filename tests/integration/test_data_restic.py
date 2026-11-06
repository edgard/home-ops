"""Exercise real Restic snapshot publication using a disposable local repository."""

import json
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from tests.support.data_generation import schema_metadata
from tests.support.runtime import load_module


def test_real_upload_publication_identity_and_partial_snapshot_exclusion(
    tmp_path, monkeypatch
):
    restic = shutil.which("restic")
    if not restic:
        pytest.fail("Install native Restic for required publication verification")
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "repo"))
    monkeypatch.setenv("RESTIC_PASSWORD", "synthetic-test-only")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(tmp_path / "cache"))
    root = tmp_path / "appdata with spaces"
    (root / ".home-ops").mkdir(parents=True)
    (root / "selfhosted/demo/.home-ops/databases").mkdir(parents=True)
    (root / "selfhosted/demo/.home-ops/databases/demo.dump").write_bytes(
        b"synthetic dump"
    )
    schema_metadata((root / "selfhosted/demo/.home-ops/databases/demo.dump"))
    (root / "selfhosted/demo/file").write_bytes(b"recoverable")
    (root / "platform-system/postgresql").mkdir(parents=True)
    (root / "platform-system/postgresql/PG_VERSION").write_text("18")
    tools = load_module("shared_data/files/data_tools.py")
    registry = {
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
            }
        },
    }
    manifest = tools.make_manifest(
        root, registry, ["demo"], "op", {"demo": ["example/demo:1"]}
    )
    (root / ".home-ops/manifest.json").write_text(json.dumps(manifest))
    subprocess.run([restic, "init"], capture_output=True, check=True)
    with patch.dict(sys.modules, {"data_tools": tools}):
        upload = load_module("shared_data/files/upload.py")
    first = upload.upload(
        "op",
        manifest,
        root=str(root),
        manifest_sha256=tools.digest(root / ".home-ops/manifest.json"),
    )
    second = upload.upload(
        "op",
        manifest,
        root=str(root),
        manifest_sha256=tools.digest(root / ".home-ops/manifest.json"),
    )
    assert first != second
    snapshots = json.loads(
        subprocess.run(
            [restic, "snapshots", "--json", "--tag", "appdata"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    )
    assert {row["id"] for row in snapshots} == {first, second}
    assert all("appdata-pending" not in row.get("tags", []) for row in snapshots)
    for snapshot in [first, second]:
        stored = subprocess.run(
            [restic, "dump", snapshot, str(root / "selfhosted/demo/file")],
            capture_output=True,
            check=True,
        ).stdout
        assert stored == b"recoverable"
        raw = subprocess.run(
            [
                restic,
                "dump",
                snapshot,
                str(root / "platform-system/postgresql/PG_VERSION"),
            ],
            capture_output=True,
        )
        assert raw.returncode != 0
    unreadable = root / "selfhosted/demo/unreadable"
    unreadable.write_bytes(b"cannot be captured")
    manifest = tools.make_manifest(
        root, registry, ["demo"], "op", {"demo": ["example/demo:1"]}
    )
    (root / ".home-ops/manifest.json").write_text(json.dumps(manifest))

    def late_permission_failure(command):
        if "backup" in command:
            unreadable.chmod(0)
        return upload.run_native(command)

    try:
        with pytest.raises(ValueError, match="incomplete"):
            upload.upload(
                "op",
                manifest,
                run=late_permission_failure,
                root=str(root),
                manifest_sha256=tools.digest(root / ".home-ops/manifest.json"),
            )
        pending = json.loads(
            subprocess.run(
                [restic, "snapshots", "--json", "--tag", "appdata-pending"],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        )
        assert len(pending) == 1
        canonical = json.loads(
            subprocess.run(
                [restic, "snapshots", "--json", "--tag", "appdata"],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        )
        assert {row["id"] for row in canonical} == {first, second}
    finally:
        unreadable.chmod(0o600)
