"""Registered native operations must acquire the shared maintenance exclusion."""

import json
import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
import yaml

from tests.integration.test_data_maintenance import (
    maintenance_api,
    obj,
    path_for,
    scenario_objects,
)
from tests.support.runtime import PLAYBOOK, ROOT, environment, executable, run_role

LEASE = (
    "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
)
JOURNAL = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"


@pytest.fixture
def native(tmp_path):
    objects, variables = scenario_objects()
    node = obj("Node", "node", "")
    node["metadata"].pop("namespace")
    node["status"] = {
        "conditions": [{"type": "Ready", "status": "True"}],
        "addresses": [{"type": "InternalIP", "address": "192.0.2.10"}],
    }
    objects.append(node)
    executable(
        tmp_path,
        "talosctl",
        """import json,os,pathlib,sys,time
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
with (base/'native.jsonl').open('a') as f:f.write(json.dumps(args)+'\\n')
if 'upgrade-k8s' in args or 'reset' in args or 'apply-config' in args:
 (base/'native-started').touch()
 while os.environ.get('NATIVE_WAIT') and not (base/'native-finish').exists():time.sleep(.02)
 if os.environ.get('NATIVE_FAIL'):sys.exit(93)
if 'version' in args:print('native-fixture')
""",
    )
    return objects, {
        **variables,
        "talos_node": "192.0.2.10",
        "talos_config_path": str(tmp_path / "synthetic-config"),
        "k8s_version": "v1.35.0",
        "node_operation_ready_retries": 3,
        "node_operation_ready_delay": 0,
    }


def invoke_native(directory, connection, variables, **kwargs):
    return run_role(
        directory, "talos", "upgrade_k8s", {**variables, **connection}, **kwargs
    )


def wait_marker(marker, future=None):
    deadline = time.monotonic() + 90
    while not marker.exists():
        if future is not None and future.done():
            result = future.result()
            pytest.fail(result.stdout + result.stderr)
        assert time.monotonic() < deadline, "native marker did not arrive"
        time.sleep(0.02)


def test_success_preserves_original_policies_and_releases_exact_owner(tmp_path, native):
    objects, variables = native
    originals = {path_for(row): deepcopy(row) for row in objects}
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "native-started").exists()
        assert state["objects"][LEASE]["spec"]["holderIdentity"] == ""
        assert state["objects"][LEASE]["metadata"]["finalizers"] == []
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        assert journal["phase"] == "complete"
        assert journal["holder"]["kind"] == "NativeCLI"
        assert journal["holder"]["original_node"] == {"name": "node", "uid": "node-uid"}
        for path, row in originals.items():
            current = deepcopy(state["objects"][path])
            original = deepcopy(row)
            current["metadata"].pop("resourceVersion", None)
            original["metadata"].pop("resourceVersion", None)
            # Controllers legitimately refresh status as replicas stop/restart.
            if (
                original["kind"] == "Deployment"
                and original["metadata"]["name"] == "tuppr"
            ):
                current.pop("status", None)
                original.pop("status", None)
            assert current == original
        snapshots = journal["snapshots"]
        assert {row["role"] for row in snapshots} == {
            "root",
            "appset",
            "application",
            "tuppr",
        }
        root_patches = [
            event
            for event in state["events"]
            if event["method"] == "PATCH"
            and event["path"].endswith("/applications/root")
        ]
        assert root_patches


@pytest.mark.parametrize(
    "entry", ["apply", "bootstrap", "upgrade", "upgrade_k8s", "reset"]
)
def test_all_registered_talos_actions_refuse_existing_owner(tmp_path, native, entry):
    objects, variables = native
    objects.append(
        obj(
            "Lease",
            "shared-data-operation",
            "selfhosted",
            {"holderIdentity": "backup:pod"},
        )
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, "talos", entry, {**variables, **connection})
        assert result.returncode != 0
        assert not (tmp_path / "native.jsonl").exists()
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_native_failure_and_new_invocation_never_release_or_reexecute(tmp_path, native):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(
            tmp_path, connection, variables, env={"NATIVE_FAIL": "1"}
        )
        assert result.returncode != 0
        lease = deepcopy(state["objects"][LEASE])
        journal = deepcopy(state["objects"][JOURNAL])
        assert lease["spec"]["holderIdentity"]
        assert lease["metadata"]["finalizers"] == ["home-ops/native-operation"]
        before = (tmp_path / "native.jsonl").read_bytes()
        again = invoke_native(tmp_path, connection, variables)
        assert again.returncode != 0
        assert state["objects"][LEASE] == lease
        assert state["objects"][JOURNAL] == journal
        assert (tmp_path / "native.jsonl").read_bytes() == before


def test_backup_cannot_acquire_between_native_preflight_and_command_completion(
    tmp_path, native
):
    objects, variables = native
    directory = tmp_path / "backup"
    directory.mkdir()
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        future = pool.submit(
            invoke_native, tmp_path, connection, variables, env={"NATIVE_WAIT": "1"}
        )
        try:
            wait_marker(tmp_path / "native-started", future)
            holder = state["objects"][LEASE]["spec"]["holderIdentity"]
            result = run_role(
                directory,
                "shared_data",
                "maintenance_hold",
                {**variables, **connection},
            )
            assert result.returncode != 0
            assert state["objects"][LEASE]["spec"]["holderIdentity"] == holder
        finally:
            (tmp_path / "native-finish").touch()
        result = future.result()
        assert result.returncode == 0, result.stdout + result.stderr


def test_original_node_replacement_after_native_success_keeps_owner(tmp_path, native):
    objects, variables = native
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        future = pool.submit(
            invoke_native, tmp_path, connection, variables, env={"NATIVE_WAIT": "1"}
        )
        try:
            wait_marker(tmp_path / "native-started", future)
            state["objects"]["/api/v1/nodes/node"]["metadata"]["uid"] = "replacement"
        finally:
            (tmp_path / "native-finish").touch()
        result = future.result()
        assert result.returncode != 0
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
        assert (
            json.loads(state["objects"][JOURNAL]["data"]["journal.json"])["phase"]
            == "native-intent"
        )


@pytest.mark.parametrize(
    "journal_state", ["intent", "complete", "missing", "old-complete"]
)
def test_watchdog_never_fences_expired_native_cli(tmp_path, native, journal_state):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(
            tmp_path, connection, variables, env={"NATIVE_FAIL": "1"}
        )
        assert result.returncode != 0
        state["objects"][LEASE]["spec"]["renewTime"] = "2000-01-01T00:00:00Z"
        if journal_state == "missing":
            del state["objects"][JOURNAL]
        elif journal_state in {"complete", "old-complete"}:
            journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
            journal["phase"] = "complete"
            if journal_state == "old-complete":
                journal["operation_id"] = "previous-backup"
                journal["operation_kind"] = "backup"
            state["objects"][JOURNAL]["data"]["journal.json"] = json.dumps(journal)
        before = deepcopy(state["objects"])
        result = run_role(
            tmp_path, "shared_data", "maintenance_watchdog", {**variables, **connection}
        )
        assert result.returncode != 0
        assert state["objects"] == before


def test_actual_local_caller_death_cannot_release_surviving_native_child(
    tmp_path, native
):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        play = tmp_path / "caller.yml"
        play.write_text(
            yaml.safe_dump(
                [
                    {
                        "hosts": "localhost",
                        "gather_facts": False,
                        "vars": {**variables, **connection, "repo_root": str(ROOT)},
                        "tasks": [
                            {
                                "ansible.builtin.include_role": {
                                    "name": "talos",
                                    "tasks_from": "upgrade_k8s",
                                }
                            }
                        ],
                    }
                ]
            )
        )
        with (tmp_path / "caller.log").open("w") as log:
            process = subprocess.Popen(
                [str(PLAYBOOK), str(play)],
                cwd=ROOT,
                env=environment(tmp_path, {"NATIVE_WAIT": "1"}),
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            try:
                wait_marker(tmp_path / "native-started")
                os.kill(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
                before = deepcopy(state["objects"])
                other = tmp_path / "other"
                other.mkdir()
                result = run_role(
                    other,
                    "shared_data",
                    "maintenance_hold",
                    {**variables, **connection},
                )
                assert result.returncode != 0
                assert state["objects"] == before
                assert state["objects"][LEASE]["spec"]["holderIdentity"]
            finally:
                (tmp_path / "native-finish").touch()
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)


@pytest.mark.parametrize("record", ["maintenance", "cold"])
def test_conflicting_journal_blocks_even_empty_lease(tmp_path, native, record):
    objects, variables = native
    journal = obj(
        "ConfigMap",
        "shared-data-operation"
        if record == "maintenance"
        else "shared-data-cold-recovery",
        "selfhosted",
    )
    journal["data"] = {
        "journal.json": json.dumps(
            {"phase": "held", "operation_id": "old", "operation_kind": "restore"}
        )
    }
    objects.append(journal)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert not (tmp_path / "native-started").exists()
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_backup_owner_prevents_native_kubernetes_upgrade(tmp_path, native):
    objects, variables = native
    lease = obj(
        "Lease",
        "shared-data-operation",
        "selfhosted",
        {
            "holderIdentity": "backup:original-pod",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    )
    with maintenance_api(tmp_path, [*objects, lease]) as (connection, state):
        result = run_role(tmp_path, "talos", "upgrade_k8s", {**variables, **connection})
        assert result.returncode != 0, result.stdout + result.stderr
        assert not (tmp_path / "native-started").exists()
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_temporary_api_reboot_outage_retries_same_owner(tmp_path, native):
    objects, variables = native
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        future = pool.submit(
            invoke_native, tmp_path, connection, variables, env={"NATIVE_WAIT": "1"}
        )
        try:
            wait_marker(tmp_path / "native-started", future)
            holder = state["objects"][LEASE]["spec"]["holderIdentity"]
            state["native_outage_reads"] = 2
        finally:
            (tmp_path / "native-finish").touch()
        result = future.result()
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["native_outage_reads"] == 0
        assert state["objects"][LEASE]["spec"]["holderIdentity"] == ""
        assert (
            json.loads(state["objects"][JOURNAL]["data"]["journal.json"])[
                "operation_id"
            ]
            == holder.split(":")[0]
        )


def test_old_owner_cannot_release_replaced_lease(tmp_path, native):
    objects, variables = native
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        future = pool.submit(
            invoke_native, tmp_path, connection, variables, env={"NATIVE_WAIT": "1"}
        )
        try:
            wait_marker(tmp_path / "native-started", future)
            state["objects"][LEASE]["spec"]["holderIdentity"] = "other:owner"
            state["objects"][LEASE]["metadata"]["resourceVersion"] = "999"
            before = deepcopy(state["objects"][LEASE])
        finally:
            (tmp_path / "native-finish").touch()
        result = future.result()
        assert result.returncode != 0
        assert state["objects"][LEASE] == before


def test_atomic_native_acquisition_has_one_winner(tmp_path, native):
    objects, variables = native
    directories = [tmp_path / name for name in ["one", "two"]]
    for directory in directories:
        directory.mkdir()
        target = directory / "talosctl"
        target.write_bytes((tmp_path / "talosctl").read_bytes())
        target.chmod(0o700)
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        futures = [
            pool.submit(
                invoke_native,
                directory,
                connection,
                variables,
                env={"NATIVE_WAIT": "1"},
            )
            for directory in directories
        ]
        try:
            deadline = time.monotonic() + 90
            while not any(
                (directory / "native-started").exists() for directory in directories
            ):
                assert time.monotonic() < deadline
                assert not all(future.done() for future in futures)
                time.sleep(0.02)
            while not any(future.done() for future in futures):
                assert time.monotonic() < deadline
                time.sleep(0.02)
            assert (
                sum(
                    (directory / "native-started").exists() for directory in directories
                )
                == 1
            )
        finally:
            for directory in directories:
                (directory / "native-finish").touch()
        results = [future.result() for future in futures]
        assert sum(result.returncode == 0 for result in results) == 1, "\n".join(
            r.stdout + r.stderr for r in results
        )


def test_kubernetes_server_version_mismatch_keeps_native_owner(tmp_path, native):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["server_version"] = "v0.0.0"
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert (tmp_path / "native-started").exists()
        assert state["objects"][LEASE]["spec"]["holderIdentity"]


@pytest.mark.parametrize("action", ["talos-apply", "cluster-create"])
def test_accepted_configuration_stays_held_and_stops_composed_mutators(
    tmp_path, native, action
):
    objects, variables = native
    variables["talos_controlplane_config_path"] = str(
        tmp_path / "synthetic-controlplane"
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "node_operation",
            "main",
            {**variables, **connection, "node_operation_action": action},
        )
        assert result.returncode != 0
        assert (tmp_path / "native-started").exists()
        commands = [
            json.loads(row)
            for row in (tmp_path / "native.jsonl").read_text().splitlines()
        ]
        assert any("apply-config" in row for row in commands)
        assert not any("bootstrap" in row for row in commands)
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
        assert (
            json.loads(state["objects"][JOURNAL]["data"]["journal.json"])["phase"]
            == "native-dispatched"
        )
        before = deepcopy(state["objects"])
        other = tmp_path / "backup-after-accepted"
        other.mkdir()
        denied = run_role(
            other, "shared_data", "maintenance_hold", {**variables, **connection}
        )
        assert denied.returncode != 0
        assert state["objects"] == before


@pytest.mark.parametrize("window", ["before-journal", "completion-response-lost"])
def test_native_crash_windows_preserve_nonrecoverable_owner(tmp_path, native, window):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["fail_native_journal_create"] = window == "before-journal"
        state["ambiguous_completion"] = window == "completion-response-lost"
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
        assert (tmp_path / "native-started").exists() == (
            window == "completion-response-lost"
        )
        if window == "before-journal":
            assert JOURNAL not in state["objects"]
        else:
            assert (
                json.loads(state["objects"][JOURNAL]["data"]["journal.json"])["phase"]
                == "complete"
            )
        before = deepcopy(state["objects"])
        blocked = run_role(
            tmp_path, "shared_data", "maintenance_watchdog", {**variables, **connection}
        )
        assert blocked.returncode != 0
        assert state["objects"] == before


def test_real_backup_hold_prevents_native_before_any_native_command(tmp_path, native):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):
        backup = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**variables, **connection}
        )
        assert backup.returncode == 0, backup.stdout + backup.stderr
        before = deepcopy(state["objects"])
        denied = invoke_native(tmp_path, connection, variables)
        assert denied.returncode != 0
        assert not (tmp_path / "native-started").exists()
        assert state["objects"] == before


def test_registered_platform_destroy_refuses_backup_owner(tmp_path, native):
    objects, variables = native
    objects.append(
        obj(
            "Lease",
            "shared-data-operation",
            "selfhosted",
            {"holderIdentity": "backup:original"},
        )
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, "platform", "destroy", {**variables, **connection})
        assert result.returncode != 0
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_talos_upgrade_cannot_uncordon_same_name_replacement(tmp_path, native):
    objects, variables = native
    node = next(row for row in objects if row["kind"] == "Node")
    node["spec"]["unschedulable"] = True
    target = yaml.safe_load(
        (ROOT / "ansible/roles/talos/defaults/main.yml").read_text()
    )["talos_upgrade"]["installer"]["version"]
    executable(
        tmp_path,
        "talosctl",
        """import json,pathlib,sys,time
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
if 'upgrade' in args:
 (base/'native-started').touch()
 while not (base/'native-finish').exists():time.sleep(.02)
elif 'version' in args:print(json.dumps({'version':{'tag':"""
        + repr(target)
        + """}}))
elif 'health' in args:pass
else:raise AssertionError(args)
""",
    )
    with (
        maintenance_api(tmp_path, objects) as (connection, state),
        ThreadPoolExecutor() as pool,
    ):
        future = pool.submit(
            run_role, tmp_path, "talos", "upgrade", {**variables, **connection}
        )
        try:
            wait_marker(tmp_path / "native-started", future)
            state["objects"]["/api/v1/nodes/node"]["metadata"].update(
                uid="replacement-node", resourceVersion="2"
            )
            replacement = deepcopy(state["objects"]["/api/v1/nodes/node"])
        finally:
            (tmp_path / "native-finish").touch()
        result = future.result()
        assert result.returncode != 0
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
        assert state["objects"]["/api/v1/nodes/node"] == replacement


@pytest.mark.parametrize("raced_field", ["uid", "resourceVersion"])
def test_native_uncordon_cas_rejects_a_change_after_its_guard(
    tmp_path, native, raced_field
):
    objects, variables = native
    node = next(row for row in objects if row["kind"] == "Node")
    node["spec"]["unschedulable"] = True
    executable(tmp_path, "talosctl", 'import sys\nassert "upgrade" in sys.argv\n')
    with maintenance_api(tmp_path, objects) as (connection, state):

        def race(path, patch, state):
            if path == "/api/v1/nodes/node" and isinstance(patch, list):
                state["objects"][path]["metadata"][raced_field] = (
                    "replacement" if raced_field == "uid" else "99"
                )
                state["raced_node"] = deepcopy(state["objects"][path])

        state["before_patch"] = race
        result = run_role(tmp_path, "talos", "upgrade", {**variables, **connection})
        assert result.returncode != 0
        assert state["objects"]["/api/v1/nodes/node"] == state["raced_node"]
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
