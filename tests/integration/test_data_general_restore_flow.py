"""Real PG18, Restic and held Ansible restores, including failure after SQL."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.integration.shared_data.test_general_recovery import adapters, registry
from tests.support.data_generation import fixture_actor, operations_image
from tests.support.runtime import ROOT, run_role

HERE = ROOT / ".pytest_cache" / "general-restore"
ROLE = ROOT / "ansible/roles/shared_data"


def docker(*args, **kwargs):
    return subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
        **kwargs,
    ).stdout.strip()


@pytest.mark.parametrize(
    "mode",
    ["file-only", "historical-file-only", "mixed", "full-cold", "partial-after-sql"],
)
def test_registered_restore_and_sql_then_file_failure(tmp_path, monkeypatch, mode):
    file_only = mode in {"file-only", "historical-file-only"}
    identifier = "general-restore-" + uuid.uuid4().hex[:12]
    directory = HERE / "runtime" / identifier
    directory.mkdir(parents=True, mode=0o700)
    tmp_path = directory / "ansible"
    tmp_path.mkdir(mode=0o700)
    pg = identifier + "-pg"
    network = identifier + "-net"
    labels = ["--label", "home-ops.test-owner=" + identifier]
    root = directory / "snapshot"
    credentials = directory / "credentials"
    credentials.mkdir()
    password = "synthetic-only"
    for key in ["postgresql_admin_password", "paperless_password", "other_password"]:
        (credentials / key).write_text(password)
    tools = adapters()
    data = registry()
    data["consumers"].pop("demo")
    for name in ["paperless", "other"]:
        data["consumers"][name] = {
            "namespace": "selfhosted",
            "enabled": True,
            "backend": "postgresql",
            "pvcs": ["selfhosted/" + name],
            "roles": [
                {
                    "name": name,
                    "password_key": name + "_password",
                    "connection_limit": 10,
                }
            ],
            "databases": [{"name": name, "owner": name}],
            "key_refs": [],
            "workloads": [{"kind": "Deployment", "name": name}],
            "cronjobs": [],
        }
    data["file_consumers"]["untouched"] = {
        "namespace": "media",
        "pvcs": ["media/untouched"],
        "workloads": [{"kind": "Deployment", "name": "untouched"}],
    }
    data["file_consumers"]["files"]["workloads"] = [
        {"kind": "Deployment", "name": "files"}
    ]
    data["consumers"]["oldsqlite"]["workloads"] = [
        {"kind": "Deployment", "name": "oldsqlite"}
    ]
    for app in [*data["consumers"].values(), *data["file_consumers"].values()]:
        path = root / app["pvcs"][0]
        path.mkdir(parents=True)
        (path / "file").write_text(app["pvcs"][0] + "-original")
    with sqlite3.connect(root / "media/oldsqlite/db.sqlite3") as db:
        db.execute("CREATE TABLE evidence(value text)")
        db.execute("INSERT INTO evidence VALUES ('original')")
    registry_file = directory / "registry.yaml"
    registry_file.write_text(yaml.safe_dump(data))
    images = {app: ["example/" + app + ":1"] for app in data["consumers"]}
    objects, variables = api.scenario_objects()
    objects = [
        obj for obj in objects if obj["metadata"]["name"] not in ["paperless", "export"]
    ]
    consumers = {**data["consumers"], **data["file_consumers"]}
    controllers = {}
    for name, app in consumers.items():
        objects.append(
            api.obj(
                "Application",
                name,
                "argocd",
                {"syncPolicy": {"automated": {"selfHeal": True, "prune": True}}},
            )
        )
        controller = api.obj(
            "Deployment",
            name,
            app["namespace"],
            {
                "replicas": 0 if mode == "full-cold" else 2,
                "selector": {"matchLabels": {"app": name}},
                "template": {
                    "spec": {
                        "containers": [
                            {"name": "app", "image": "example/" + name + ":1"}
                        ]
                    }
                },
            },
        )
        objects.append(controller)
        controllers[name] = controller
    if mode == "full-cold":
        objects[0]["spec"]["syncPolicy"].pop("automated")
    scope = ["files"] if file_only else ["paperless", "files", "oldsqlite"]
    if mode == "historical-file-only":
        scope = ["files", "oldsqlite"]
    if mode == "full-cold":
        scope = ["paperless", "other", "oldsqlite", "files", "untouched"]
    env = {
        "RESTIC_REPOSITORY": str(directory / "repository"),
        "RESTIC_PASSWORD": "synthetic-only",
        "RESTIC_CACHE_DIR": str(directory / "cache"),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    def client(script, *args):
        return docker(
            "run",
            "--rm",
            *fixture_actor(),
            "--network",
            network,
            "--entrypoint",
            "python",
            "-v",
            str(directory) + ":" + str(directory),
            "-v",
            str(ROLE) + ":" + str(ROLE) + ":ro",
            operations_image(),
            str(ROLE / "files" / script),
            *args,
        )

    def sql(database, statement):
        return docker(
            "exec", pg, "psql", "-U", "postgres", "-d", database, "-Atc", statement
        )

    try:
        docker("network", "create", *labels, network)
        docker(
            "run",
            "-d",
            "--name",
            pg,
            *labels,
            "--network",
            network,
            "--tmpfs",
            "/var/lib/postgresql",
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "postgres:18.3-trixie",
        )
        for _ in range(120):
            if (
                subprocess.run(
                    ["docker", "exec", pg, "pg_isready", "-U", "postgres"],
                    capture_output=True,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.25)
        else:
            pytest.fail("synthetic PG18 did not become ready")
        common = [
            "--registry",
            str(registry_file),
            "--apps",
            "paperless,other",
            "--credentials",
            str(credentials),
            "--pg-host",
            pg,
        ]
        client("data_tools.py", "provision", *common, "--confirm")
        for name in ["paperless", "other"]:
            sql(
                name,
                "CREATE TABLE evidence(id bigserial PRIMARY KEY,value text); INSERT INTO evidence(value) VALUES ('original');",
            )
        sql("postgres", "CREATE DATABASE foreign_db")
        sql(
            "foreign_db",
            "CREATE TABLE evidence(value text); INSERT INTO evidence VALUES ('foreign-untouched')",
        )
        client("data_tools.py", "dump", *common, "--root", str(root), "--confirm")
        manifest = tools["data_tools"].make_manifest(
            root, data, ["paperless", "other"], "capture", images
        )
        (root / ".home-ops").mkdir()
        manifest_file = root / ".home-ops/manifest.json"
        manifest_file.write_text(json.dumps(manifest))
        subprocess.run(["restic", "init"], capture_output=True, check=True)
        snapshot = tools["upload"].upload(
            "capture",
            manifest,
            root=str(root),
            manifest_sha256=hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
            registry=data,
            apps=["paperless", "other"],
            legacy_pvcs=["media/files", "media/oldsqlite", "media/untouched"],
        )
        if mode == "historical-file-only":
            manifest_file.unlink()
            output = subprocess.run(
                [
                    "restic",
                    "backup",
                    str(root),
                    "--host",
                    "homelab",
                    "--tag",
                    "appdata",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            snapshot = [
                json.loads(row)["snapshot_id"]
                for row in output.splitlines()
                if json.loads(row).get("message_type") == "summary"
            ][0]
        for name in ["paperless", "other"]:
            sql(name, "UPDATE evidence SET value='new-write'")
        live = directory / "live"
        shutil.copytree(root, live)
        for app in consumers.values():
            (live / app["pvcs"][0] / "file").write_text(app["pvcs"][0] + "-new-write")
        with sqlite3.connect(live / "media/oldsqlite/db.sqlite3") as db:
            db.execute("UPDATE evidence SET value='new-write'")
        reserved = live / "platform-system/postgresql/PG_VERSION"
        reserved.parent.mkdir(parents=True)
        reserved.write_text("18-untouched")
        wrapper = directory / "native-python"
        wrapper.write_text(
            "#!"
            + sys.executable
            + "\n"
            + f"""
import os,subprocess,sys
cmd=['docker','run','--rm', *{fixture_actor()!r},'--network',{network!r},'--entrypoint','python','-v',{str(directory) + ":" + str(directory)!r},'-v',{str(ROLE) + ":" + str(ROLE) + ":ro"!r}]
for name in ['TMPDIR','HOME_OPS_DATA_DEADLINE','RESTIC_REPOSITORY','RESTIC_PASSWORD','RESTIC_CACHE_DIR']:
    if name in os.environ:cmd += ['-e',name+'='+os.environ[name]]
args=sys.argv[1:]
if args[0].endswith(('data_tools.py','recovery.py')):args += ['--pg-host',{pg!r}]
r=subprocess.run(cmd+[{operations_image()!r}]+args,capture_output=True)
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
            shared_data_apps=scope,
            shared_data_registry=data,
            shared_data_drain_enabled=True,
            shared_data_recovery_budget=900,
            shared_data_lease_duration=1200,
            shared_data_image=operations_image(native=False),
            shared_data_root=str(live),
            shared_data_snapshot_root=str(root),
            shared_data_staging=str(directory / "staging"),
            shared_data_credentials=str(credentials),
            shared_data_registry_file=str(registry_file),
            shared_data_python=str(wrapper),
            shared_data_tools=str(ROLE / "files/data_tools.py"),
        )
        journal_path = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"

        def patched(path, value, state):
            root_object = state["objects"][api.path_for(objects[0])]
            # A self-healing root would immediately restore child automation.
            if (
                value["kind"] == "Application"
                and value["metadata"]["name"] != "root"
                and "automated" not in value["spec"].get("syncPolicy", {})
            ):
                assert "automated" not in root_object["spec"]["syncPolicy"]
                state["selfheal_fenced"] = True
            if (
                value["kind"] == "Deployment"
                and value["metadata"]["name"] in scope
                and value["spec"]["replicas"] == 0
            ):
                journal = json.loads(
                    state["objects"][journal_path]["data"]["journal.json"]
                )
                assert journal["recovery"]["snapshot"] == snapshot
                assert len(journal["recovery"]["selection_sha256"]) == 64
                assert (
                    Path(journal["recovery"]["root"]) / "media/files/file"
                ).read_text() == "media/files-original"
                state["selected_stopped"] = True
                if mode == "partial-after-sql" and not state.get("invalid_destination"):
                    target = live / "media/files"
                    shutil.rmtree(target)
                    target.symlink_to(
                        live / "media/untouched", target_is_directory=True
                    )
                    state["invalid_destination"] = True

        with api.maintenance_api(tmp_path, objects) as (connection, state):
            state["patched"] = patched
            result = run_role(
                tmp_path,
                str(ROLE),
                "main",
                {**connection, **variables},
                env={
                    **env,
                    "DOCKER_HOST": docker(
                        "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
                    ),
                },
                timeout=900,
            )
            diagnostic = (
                (directory / "native.log").read_text()
                if (directory / "native.log").exists()
                else ""
            )
            assert (result.returncode == 0) == (mode != "partial-after-sql"), (
                result.stdout[-22000:] + result.stderr + diagnostic
            )
            journal = json.loads(state["objects"][journal_path]["data"]["journal.json"])
            assert journal["recovery"]["snapshot"] == snapshot
            assert state.get("selected_stopped")
            assert state.get("selfheal_fenced")
            assert (
                sql("foreign_db", "SELECT value FROM evidence") == "foreign-untouched"
            )
            assert reserved.read_text() == "18-untouched"
            assert sql("paperless", "SELECT value FROM evidence") == (
                "new-write" if file_only else "original"
            )
            assert sql("other", "SELECT value FROM evidence") == (
                "original" if mode == "full-cold" else "new-write"
            )
            assert (live / "media/untouched/file").read_text() == (
                "media/untouched-original"
                if mode == "full-cold"
                else "media/untouched-new-write"
            )
            if mode == "partial-after-sql":
                assert state["invalid_destination"]
                assert journal["phase"] == "held"
                assert (
                    live / "selfhosted/paperless/file"
                ).read_text() == "selfhosted/paperless-new-write"
                assert (
                    live / "media/oldsqlite/file"
                ).read_text() == "media/oldsqlite-new-write"
                assert (
                    "automated"
                    not in state["objects"][api.path_for(objects[0])]["spec"][
                        "syncPolicy"
                    ]
                )
                for name in scope:
                    assert (
                        state["objects"][api.path_for(controllers[name])]["spec"][
                            "replicas"
                        ]
                        == 0
                    )
            else:
                assert journal["phase"] == "complete"
                for name in scope:
                    assert (
                        live / consumers[name]["pvcs"][0] / "file"
                    ).read_text() == consumers[name]["pvcs"][0] + "-original"
                    assert state["objects"][api.path_for(controllers[name])]["spec"][
                        "replicas"
                    ] == (0 if mode == "full-cold" else 2)
                with sqlite3.connect(live / "media/oldsqlite/db.sqlite3") as db:
                    assert db.execute("SELECT value FROM evidence").fetchone()[0] == (
                        "new-write" if mode == "file-only" else "original"
                    )
                root_spec = state["objects"][api.path_for(objects[0])]["spec"]
                assert ("automated" in root_spec["syncPolicy"]) == (mode != "full-cold")
                if mode != "full-cold":
                    patches = [
                        event
                        for event in state["events"]
                        if event["method"] == "PATCH"
                        and event["path"]
                        in [
                            api.path_for(o) for o in objects if o["kind"] not in ["Pod"]
                        ]
                    ]
                    assert patches[-1]["path"] == api.path_for(objects[0])
    finally:
        subprocess.run(["docker", "rm", "-fv", pg], capture_output=True, timeout=60)
        subprocess.run(
            ["docker", "network", "rm", network], capture_output=True, timeout=60
        )
        shutil.rmtree(directory)
