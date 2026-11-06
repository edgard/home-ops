"""The real held restore role changes only the selected application."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.integration.shared_data.test_recovery import load_adapter
from tests.support.data_generation import fixture_actor, operations_image
from tests.support.runtime import ROOT, run_role


@pytest.mark.parametrize("mode", ["restore", "changed-stage", "cold"])
def test_selected_restore_and_failed_validation_hold(tmp_path, monkeypatch, mode):
    directory = ROOT / ".pytest_cache" / ("restore-flow-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, mode=0o700)
    snapshot_root = directory / "snapshot"
    source = snapshot_root / "selfhosted/paperless"
    source.mkdir(parents=True)
    (source / "file").write_text("original")
    with sqlite3.connect(source / "source.db") as db:
        db.execute("CREATE TABLE evidence(value text)")
        db.execute("INSERT INTO evidence VALUES ('original')")
    objects, variables = api.scenario_objects()
    registry = variables["shared_data_registry"]
    registry["consumers"]["paperless"].update(
        backend="sqlite",
        roles=[],
        databases=[],
        pvcs=["selfhosted/paperless"],
        sqlite_files=["selfhosted/paperless/source.db"],
        key_refs=[],
    )
    (directory / "registry.yaml").write_text(yaml.safe_dump(registry))
    tools = load_adapter("data_tools")
    manifest = tools.make_manifest(
        snapshot_root,
        registry,
        ["paperless"],
        "capture",
        {"paperless": ["example/paperless:1"]},
    )
    (snapshot_root / ".home-ops").mkdir()
    (snapshot_root / ".home-ops/manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setenv("RESTIC_REPOSITORY", str(directory / "repository"))
    monkeypatch.setenv("RESTIC_PASSWORD", "synthetic-only")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(directory / "cache"))
    subprocess.run(["restic", "init"], capture_output=True, check=True)
    snapshot = load_adapter("upload").upload(
        "capture",
        manifest,
        root=str(snapshot_root),
        manifest_sha256=hashlib.sha256(
            (snapshot_root / ".home-ops/manifest.json").read_bytes()
        ).hexdigest(),
    )
    live_root = directory / "live"
    live = live_root / "selfhosted/paperless"
    live.mkdir(parents=True)
    if mode != "cold":
        (live / "file").write_text("new-write")
        with sqlite3.connect(live / "source.db") as db:
            db.execute("CREATE TABLE evidence(value text)")
            db.execute("INSERT INTO evidence VALUES ('new-write')")
    other = live_root / "selfhosted/other/file"
    other.parent.mkdir()
    other.write_text("unchanged")
    deployment = next(
        o
        for o in objects
        if o["kind"] == "Deployment" and o["metadata"]["name"] == "paperless"
    )
    deployment["spec"]["template"] = {
        "spec": {"containers": [{"name": "app", "image": "example/paperless:1"}]}
    }
    if mode == "cold":
        deployment["spec"]["replicas"] = 0
        objects[0]["spec"]["syncPolicy"].pop("automated")
    wrapper = directory / "native-python"
    wrapper.write_text(
        "#!"
        + sys.executable
        + "\n"
        + f"""
import os,subprocess,sys
cmd=['docker','run','--rm', *{fixture_actor()!r},'--network','none','--entrypoint','python','-v',{str(directory) + ":" + str(directory)!r},'-v',{str(ROOT / "ansible/roles/shared_data") + ":" + str(ROOT / "ansible/roles/shared_data") + ":ro"!r}]
for name in ['TMPDIR','HOME_OPS_DATA_DEADLINE','RESTIC_REPOSITORY','RESTIC_PASSWORD','RESTIC_CACHE_DIR']:
    if name in os.environ:cmd += ['-e',name+'='+os.environ[name]]
r=subprocess.run(cmd+[{operations_image()!r}]+sys.argv[1:],capture_output=True)
with open({str(directory / "native.log")!r},'ab') as log:log.write(r.stdout+r.stderr)
sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr)
raise SystemExit(r.returncode)
"""
    )
    wrapper.chmod(0o700)
    variables.update(
        shared_data_action="restore",
        shared_data_operation_kind="restore",
        shared_data_operation_id="test-restore",
        shared_data_recovery_budget=600,
        shared_data_image=operations_image(native=False),
        shared_data_root=str(live_root),
        shared_data_snapshot_root=str(snapshot_root),
        shared_data_staging=str(directory / "staging"),
        shared_data_credentials=str(directory / "credentials"),
        shared_data_registry_file=str(directory / "registry.yaml"),
        shared_data_python=str(wrapper),
        shared_data_tools=str(ROOT / "ansible/roles/shared_data/files/data_tools.py"),
    )
    (directory / "credentials").mkdir()

    def patched(path, value, state):
        if (
            mode == "changed-stage"
            and path == api.path_for(deployment)
            and value["spec"]["replicas"] == 0
            and not state.get("corrupted")
        ):
            restored = (
                directory
                / "staging/restores/test-restore"
                / str(snapshot_root).lstrip("/")
                / "selfhosted/paperless/file"
            )
            assert restored.is_file()
            restored.write_text("corrupted")
            state["corrupted"] = True

    try:
        with api.maintenance_api(tmp_path, objects) as (connection, state):
            state["patched"] = patched
            endpoint = subprocess.run(
                [
                    "docker",
                    "context",
                    "inspect",
                    "--format",
                    "{{.Endpoints.docker.Host}}",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            result = run_role(
                tmp_path,
                "shared_data",
                "main",
                {**connection, **variables},
                env={
                    "DOCKER_HOST": endpoint,
                    "RESTIC_REPOSITORY": str(directory / "repository"),
                    "RESTIC_PASSWORD": "synthetic-only",
                    "RESTIC_CACHE_DIR": str(directory / "cache"),
                },
                timeout=300,
            )
            diagnostic = (
                (directory / "native.log").read_text()
                if (directory / "native.log").exists()
                else ""
            )
            assert (result.returncode == 0) == (mode != "changed-stage"), (
                result.stdout[-18000:] + result.stderr + diagnostic
            )
            journal = json.loads(
                state["objects"][
                    "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
                ]["data"]["journal.json"]
            )
            assert journal["recovery"]["snapshot"] == snapshot
            assert other.read_text() == "unchanged"
            if mode == "changed-stage":
                assert state["corrupted"]
                assert journal["phase"] == "held"
                assert (
                    state["objects"][api.path_for(deployment)]["spec"]["replicas"] == 0
                )
                assert (live / "file").read_text() == "new-write"
                assert not state["objects"][api.path_for(objects[0])]["spec"][
                    "syncPolicy"
                ].get("automated")
            else:
                assert journal["phase"] == "complete"
                assert (live / "file").read_text() == "original"
                with sqlite3.connect(live / "source.db") as db:
                    assert db.execute("SELECT value FROM evidence").fetchall() == [
                        ("original",)
                    ]
                assert state["objects"][api.path_for(deployment)]["spec"][
                    "replicas"
                ] == (0 if mode == "cold" else 2)
                if mode == "cold":
                    assert not state["objects"][api.path_for(objects[0])]["spec"][
                        "syncPolicy"
                    ].get("automated")
    finally:
        shutil.rmtree(directory)
