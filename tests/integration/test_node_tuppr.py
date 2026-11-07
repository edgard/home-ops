"""Native owners must durably exclude independent automatic upgrade workers."""

import json
from copy import deepcopy

import pytest

from tests.integration.test_data_maintenance import maintenance_api, obj, path_for
from tests.integration.test_node_operation import (
    JOURNAL,
    LEASE,
    invoke_native,
)
from tests.integration.test_node_operation import (
    native as native_fixture,
)

native = native_fixture


def upgrade_job():
    job = obj("Job", "automatic-upgrade", "platform-system", {"backoffLimit": 6})
    job["metadata"]["labels"] = {
        "app.kubernetes.io/part-of": "tuppr",
        "app.kubernetes.io/name": "kubernetes-upgrade",
    }
    return job


@pytest.mark.parametrize("state_kind", ["active", "restart-capable", "pod-only"])
def test_native_refuses_independent_automatic_worker(tmp_path, native, state_kind):
    objects, variables = native
    job = upgrade_job()
    if state_kind == "active":
        job["status"] = {"active": 1}
    elif state_kind == "restart-capable":
        job["status"] = {"failed": 1}
    if state_kind == "pod-only":
        pod = obj("Pod", "orphan-upgrade", "platform-system")
        pod["metadata"]["labels"] = job["metadata"]["labels"]
        pod["status"] = {"phase": "Running"}
        objects.append(pod)
    else:
        objects.append(job)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert not (tmp_path / "native-started").exists()
        assert state["objects"][LEASE]["spec"]["holderIdentity"]


def test_native_catches_worker_launched_as_controller_stops(tmp_path, native):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):

        def launch(path, value, state):
            if path.endswith("/deployments/tuppr") and value["spec"]["replicas"] == 0:
                job = upgrade_job()
                state["objects"][path_for(job)] = job
                state["boundary_launch"] = True

        state["patched"] = launch
        result = invoke_native(tmp_path, connection, variables)
        assert state.get("boundary_launch"), result.stdout + result.stderr
        assert result.returncode != 0
        assert not (tmp_path / "native-started").exists()
        assert state["objects"][LEASE]["spec"]["holderIdentity"]


def test_failed_native_preserves_durable_minimal_fences(tmp_path, native):
    objects, variables = native
    writers = {
        path_for(row): deepcopy(row)
        for row in objects
        if row["metadata"]["name"] in {"paperless", "export"}
    }
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(
            tmp_path, connection, variables, env={"NATIVE_FAIL": "1"}
        )
        assert result.returncode != 0
        assert (tmp_path / "native-started").exists()
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        assert {r["role"] for r in journal["snapshots"]} == {
            "root",
            "appset",
            "application",
            "tuppr",
        }
        for row in journal["snapshots"]:
            current = state["objects"][
                path_for(
                    {
                        "apiVersion": row["api_version"],
                        "kind": row["kind"],
                        "metadata": row,
                    }
                )
            ]
            if row["role"] in {"root", "application"}:
                assert "automated" not in current["spec"]["syncPolicy"]
                assert (
                    current["metadata"]["annotations"][
                        "argocd.argoproj.io/skip-reconcile"
                    ]
                    == "true"
                )
            elif row["role"] == "appset":
                assert (
                    current["spec"]["syncPolicy"]["applicationsSync"] == "create-only"
                )
            else:
                assert current["spec"]["replicas"] == 0
        assert all(state["objects"][p] == row for p, row in writers.items())


@pytest.mark.parametrize("change", ["source", "queued", "cas"])
def test_native_refuses_foreign_change_at_fence_boundary(tmp_path, native, change):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):

        def race(path, patch, state):
            if not path.endswith("/applications/tuppr") or state.get("injected"):
                return
            current = state["objects"][path]
            if change == "source":
                current["spec"]["source"] = {"targetRevision": "foreign"}
            elif change == "queued":
                current["operation"] = {"sync": {"revision": "foreign"}}
            current["metadata"]["resourceVersion"] = "99"
            state["injected"] = True
            state["foreign"] = deepcopy(current)

        state["before_patch"] = race
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert state.get("injected"), result.stdout + result.stderr
        assert not (tmp_path / "native-started").exists()
        if change != "cas":
            assert (
                state["objects"][
                    "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/tuppr"
                ]
                == state["foreign"]
            )
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/platform-system/deployments/tuppr"
            ]["spec"]["replicas"]
            == 0
        )
        assert state["objects"][LEASE]["spec"]["holderIdentity"]


def test_native_success_restores_exact_fences_with_root_last(tmp_path, native):
    objects, variables = native
    originals = {
        path_for(row): deepcopy(row)
        for row in objects
        if row["metadata"]["name"] in {"root", "apps", "tuppr"}
    }
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode == 0, result.stdout + result.stderr
        for path, original in originals.items():
            current = state["objects"][path]
            assert current["spec"] == original["spec"]
            assert current["metadata"].get("annotations") == original["metadata"].get(
                "annotations"
            )
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        assert journal["phase"] == "complete"
        critical = [
            i
            for i, e in enumerate(state["events"])
            if e["method"] == "PATCH"
            and e["path"] == JOURNAL
            and any(
                p.get("path") == "/data/journal.json"
                and json.loads(p["value"])["phase"] == "native-critical-complete"
                for p in e["body"]
            )
        ]
        assert critical
        changed = [
            e["path"]
            for e in state["events"][critical[-1] + 1 :]
            if e["method"] == "PATCH" and e["path"] in originals
        ]
        assert changed[-1].endswith("/applications/root")
        assert state["objects"][LEASE]["spec"]["holderIdentity"] == ""


def test_failed_restore_fences_remaining_targets_after_foreign_root_request(
    tmp_path, native
):
    objects, variables = native
    with maintenance_api(tmp_path, objects) as (connection, state):

        def queue_after_resume(path, value, state):
            if path.endswith("/deployments/tuppr") and value["spec"]["replicas"] == 1:
                root = state["objects"][
                    "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
                ]
                root["operation"] = {"sync": {"revision": "foreign-queued"}}
                root["metadata"]["resourceVersion"] = "99"
                state["foreign_root"] = deepcopy(root)

        state["patched"] = queue_after_resume
        result = invoke_native(tmp_path, connection, variables)
        assert result.returncode != 0
        assert (tmp_path / "native-started").exists()
        assert (
            state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]
            == state["foreign_root"]
        )
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/platform-system/deployments/tuppr"
            ]["spec"]["replicas"]
            == 0
        )
        assert (
            state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/tuppr"
            ]["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"]
            == "true"
        )
        assert state["objects"][LEASE]["spec"]["holderIdentity"]
        assert (
            json.loads(state["objects"][JOURNAL]["data"]["journal.json"])["phase"]
            == "native-critical-complete"
        )
