"""Real role, Linux capture/upload adapters, Restic, and synthetic Kubernetes API."""

import json
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.support.data_generation import fixture_actor, operations_image
from tests.support.runtime import ROOT, run_role


def image():
    return operations_image()


def wait_for_resumed_writer(state, path, coordinator_done):
    """Bound the fixture's upload wait and stop when its coordinator fails."""
    deadline = time.monotonic() + 600
    while True:
        if coordinator_done.is_set():
            raise AssertionError("coordinator ended before writers resumed")
        if state["objects"][path]["spec"]["replicas"] == 2:
            return
        if time.monotonic() > deadline:
            raise AssertionError("writers never resumed before upload")
        coordinator_done.wait(0.1)


def test_uploader_fixture_stops_waiting_after_failed_coordinator():
    state = {"objects": {"writer": {"spec": {"replicas": 0}}}}
    done = threading.Event()
    errors = []
    uploaded = []

    def upload():
        try:
            wait_for_resumed_writer(state, "writer", done)
            uploaded.append(True)
        except AssertionError as error:
            errors.append(str(error))

    worker = threading.Thread(target=upload)
    worker.start()
    try:
        worker.join(timeout=0.05)
        assert worker.is_alive()
    finally:
        done.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert errors == ["coordinator ended before writers resumed"]
    state["objects"]["writer"]["spec"]["replicas"] = 2
    assert not uploaded


def test_uploader_fixture_refuses_already_resumed_writer_after_coordinator_exit():
    state = {"objects": {"writer": {"spec": {"replicas": 2}}}}
    done = threading.Event()
    done.set()
    with pytest.raises(
        AssertionError, match="coordinator ended before writers resumed"
    ):
        wait_for_resumed_writer(state, "writer", done)


@pytest.mark.parametrize("broken_images", [False, True])
def test_backup_captures_then_resumes_before_fresh_upload(tmp_path, broken_images):
    objects, variables = api.scenario_objects()
    directory = ROOT / ".pytest_cache" / ("backup-flow-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, mode=0o700)
    root = directory / "appdata"
    pvc = root / "selfhosted/paperless"
    pvc.mkdir(parents=True)
    with sqlite3.connect(pvc / "db.sqlite3") as db:
        db.execute("CREATE TABLE evidence(value text)")
        db.execute("INSERT INTO evidence VALUES ('retained')")
    (pvc / "file").write_text("captured")
    registry = variables["shared_data_registry"]
    registry["consumers"]["paperless"].update(
        backend="sqlite",
        roles=[],
        databases=[],
        pvcs=["selfhosted/paperless"],
        sqlite_files=["selfhosted/paperless/db.sqlite3"],
        key_refs=[],
    )
    (directory / "registry.yaml").write_text(yaml.safe_dump(registry))
    deployment = next(
        o
        for o in objects
        if o["kind"] == "Deployment" and o["metadata"]["name"] == "paperless"
    )
    if not broken_images:
        deployment["spec"]["template"] = {
            "spec": {"containers": [{"name": "app", "image": "example/paperless:1"}]}
        }
    wrapper = directory / "native-python"
    wrapper.write_text(
        "#!"
        + sys.executable
        + "\n"
        + f"""
import os, subprocess, sys
command = ['docker', 'run', '--rm', *{fixture_actor()!r}, '--network', 'none', '--entrypoint', 'python', '-v', {str(directory) + ":" + str(directory)!r}, '-v', {str(ROOT / "ansible/roles/shared_data") + ":" + str(ROOT / "ansible/roles/shared_data") + ":ro"!r}]
for name in ['TMPDIR', 'HOME_OPS_DATA_DEADLINE']:
    if name in os.environ:
        command += ['-e', name + '=' + os.environ[name]]
result = subprocess.run(command + [{image()!r}] + sys.argv[1:], capture_output=True)
with open({str(directory / "native.log")!r}, 'ab') as stream:
    stream.write(result.stdout + result.stderr)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
"""
    )
    wrapper.chmod(0o700)
    variables.update(
        shared_data_action="backup",
        shared_data_image=operations_image(native=False),
        shared_data_python=str(wrapper),
        shared_data_tools=str(ROOT / "ansible/roles/shared_data/files/data_tools.py"),
        shared_data_registry_file=str(directory / "registry.yaml"),
        shared_data_root=str(root),
        shared_data_staging=str(directory / "staging"),
        shared_data_credentials=str(directory / "credentials"),
        shared_data_job_timeout=300,
    )
    (directory / "credentials").mkdir()
    (directory / "bin").mkdir()
    restic_wrapper = directory / "bin/restic"
    restic_wrapper.write_text(
        "#!/usr/local/bin/python\nimport os,subprocess,sys\nr=subprocess.run(['/usr/local/bin/restic']+sys.argv[1:],capture_output=True)\nwith open('/fixture/restic.log','ab') as f: f.write(r.stderr)\nsys.stdout.buffer.write(r.stdout)\nsys.stderr.buffer.write(r.stderr)\nraise SystemExit(r.returncode)\n"
    )
    restic_wrapper.chmod(0o700)

    errors = []
    workers = []
    job_results = []
    coordinator_done = threading.Event()

    def created(job, state):
        def execute():
            try:
                wait_for_resumed_writer(
                    state, api.path_for(deployment), coordinator_done
                )
                # Replay the Pod mounts with one bind-fixture identity. Explicit
                # production UID/capability behavior has separate Linux coverage.
                mounts = [
                    "-v",
                    str(ROOT / "ansible/roles/shared_data")
                    + ":/opt/home-ops/ansible/roles/shared_data:ro",
                ]
                volumes = {
                    "appdata": root,
                    "staging": directory / "staging",
                    "credentials": directory / "credentials",
                    "registry": directory,
                }
                for mount in job["spec"]["template"]["spec"]["containers"][0][
                    "volumeMounts"
                ]:
                    if mount["name"] in {"tmp", "canonical"}:
                        continue
                    source = volumes[mount["name"]] / mount.get("subPath", "")
                    if mount["name"] == "registry":
                        source = directory / "registry.yaml"
                    mounts += [
                        "-v",
                        str(source)
                        + ":"
                        + mount["mountPath"]
                        + (":ro" if mount.get("readOnly") else ""),
                    ]
                env = {
                    "RESTIC_REPOSITORY": "/fixture/repository",
                    "RESTIC_PASSWORD": "synthetic-only",
                    "RESTIC_CACHE_DIR": "/tmp/cache",
                    "HOME": "/tmp",
                    "PATH": "/fixture/bin:/usr/lib/postgresql/18/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "ANSIBLE_LOCAL_TEMP": "/tmp/ansible-local",
                    "ANSIBLE_REMOTE_TEMP": "/tmp/ansible-remote",
                }
                command = [
                    "docker",
                    "run",
                    "--rm",
                    *fixture_actor(),
                    "--network",
                    "none",
                    "-v",
                    str(directory) + ":/fixture",
                    *mounts,
                ]
                for key, value in env.items():
                    command += ["-e", key + "=" + value]
                init = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        *fixture_actor(),
                        "--network",
                        "none",
                        "--entrypoint",
                        "restic",
                        "-v",
                        str(directory) + ":/fixture",
                        "-e",
                        "RESTIC_REPOSITORY=/fixture/repository",
                        "-e",
                        "RESTIC_PASSWORD=synthetic-only",
                        image(),
                        "init",
                    ],
                    capture_output=True,
                    text=True,
                )
                assert init.returncode == 0, init.stderr
                command += [
                    image(),
                    *job["spec"]["template"]["spec"]["containers"][0]["args"],
                ]
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=180
                )
                job_results.append(result)
                if result.returncode:
                    # Synthetic-only diagnostics use identical mounts and adapter inputs.
                    details = json.loads(
                        job["spec"]["template"]["spec"]["containers"][0]["args"][-1]
                    )
                    debug = command[: command.index(image())] + [
                        "--entrypoint",
                        "python",
                        image(),
                        "/opt/home-ops/ansible/roles/shared_data/files/upload.py",
                        "--operation",
                        variables["shared_data_operation_id"],
                        "--apps",
                        "paperless",
                        "--manifest-sha256",
                        details["shared_data_manifest_sha256"],
                        "--receipt",
                        "/staging/uploaded/test-backup.json",
                    ]
                    diagnostic = subprocess.run(
                        debug, capture_output=True, text=True, timeout=180
                    )
                    raise AssertionError(
                        result.stdout
                        + result.stderr
                        + diagnostic.stdout
                        + diagnostic.stderr
                    )
                state["objects"][api.path_for(job)]["status"] = {
                    "conditions": [{"type": "Complete", "status": "True"}]
                }
            except BaseException as error:
                errors.append(error)
                state["objects"][api.path_for(job)]["status"] = {
                    "conditions": [{"type": "Failed", "status": "True"}]
                }

        thread = threading.Thread(target=execute)
        workers.append(thread)
        thread.start()

    try:
        with api.maintenance_api(tmp_path, objects) as (connection, state):
            state["job_created"] = created

            def paused(path, value, state):
                if path == api.path_for(deployment) and value["spec"]["replicas"] == 0:
                    state.setdefault("producer_paused_at", time.time())

            state["patched"] = paused
            try:
                result = run_role(
                    tmp_path,
                    "shared_data",
                    "main",
                    {**connection, **variables},
                    env={
                        "DOCKER_HOST": subprocess.run(
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
                    },
                    timeout=900,
                    after=(
                        [
                            {
                                "ansible.builtin.copy": {
                                    "content": "{{ shared_data_capture_deadline | to_json }}",
                                    "dest": str(directory / "deadline.json"),
                                    "mode": "0600",
                                }
                            }
                        ]
                        if not broken_images
                        else []
                    ),
                )
            finally:
                coordinator_done.set()
            for worker in workers:
                worker.join(timeout=190)
            assert not errors, "\n".join(str(error) for error in errors) + (
                (directory / "restic.log").read_text()
                if (directory / "restic.log").exists()
                else ""
            )
            assert (result.returncode == 0) is not broken_images, (
                result.stdout[-14000:]
                + result.stderr
                + (directory / "native.log").read_text()
            )
            assert state["objects"][api.path_for(deployment)]["spec"]["replicas"] == 2
            journal = json.loads(
                state["objects"][
                    "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
                ]["data"]["journal.json"]
            )
            assert journal["phase"] == "complete"
            assert not state["objects"][
                "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
            ]["spec"]["holderIdentity"]
            if broken_images:
                assert not workers
                assert "Build captured image mapping" in result.stdout
                assert not (directory / "staging/generations/test-backup").exists()
            else:
                assert len(job_results) == 1
                deadline = json.loads((directory / "deadline.json").read_text())
                assert deadline <= state["producer_paused_at"] + variables.get(
                    "shared_data_pause_budget", 180
                ), (
                    "capture budget must include the producer pause, not restart after draining"
                )
                receipt = json.loads(
                    (directory / "staging/uploaded/test-backup.json").read_text()
                )
                assert len(receipt["snapshot"]) == 64
                manifest = (
                    directory
                    / "staging/generations/test-backup/.home-ops/manifest.json"
                )
                assert (
                    journal["manifest_sha256"]
                    == __import__("hashlib").sha256(manifest.read_bytes()).hexdigest()
                )
                assert (
                    receipt["captured_at"]
                    == json.loads(manifest.read_text())["captured_at"]
                )
                assert (
                    state["objects"][
                        "/api/v1/namespaces/selfhosted/configmaps/shared-data-backup-status"
                    ]["data"]["captured_at"]
                    == receipt["captured_at"]
                )
            assert (pvc / "file").read_text() == "captured"
            with sqlite3.connect(pvc / "db.sqlite3") as db:
                assert db.execute("SELECT * FROM evidence").fetchall() == [
                    ("retained",)
                ]
    finally:
        coordinator_done.set()
        for worker in workers:
            worker.join(timeout=190)
        if not any(worker.is_alive() for worker in workers):
            shutil.rmtree(directory)
