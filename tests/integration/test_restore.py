import json
import shlex

import pytest

from tests.support.api import cluster_api, pod_exec_collection
from tests.support.runtime import ROOT, run_role
from tests.support.sources import read_yaml

PREFIX = {
    "Application": "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/",
    "ApplicationSet": "/apis/argoproj.io/v1alpha1/namespaces/argocd/applicationsets/",
    "Deployment": "/apis/apps/v1/namespaces/",
    "StatefulSet": "/apis/apps/v1/namespaces/",
    "PersistentVolumeClaim": "/api/v1/namespaces/",
}


@pytest.fixture
def restore(tmp_path):
    data = read_yaml(ROOT / "tests/fixtures/restore.yaml")
    objects = {}
    for app in data["applications"]:
        app.update(apiVersion="argoproj.io/v1alpha1", kind="Application")
        app["metadata"]["namespace"] = "argocd"
        app["spec"]["syncPolicy"] = {
            "automated": {"prune": True},
            "retry": {"limit": 2},
        }
        objects[PREFIX["Application"] + app["metadata"]["name"]] = app
    for pvc in data["pvcs"]:
        pvc.update(apiVersion="v1", kind="PersistentVolumeClaim")
        objects[
            "/api/v1/namespaces/"
            + pvc["metadata"]["namespace"]
            + "/persistentvolumeclaims/"
            + pvc["metadata"]["name"]
        ] = pvc
    for i, workload in enumerate(data["workloads"]):
        workload["apiVersion"] = "apps/v1"
        workload["spec"]["replicas"] = i
        objects[
            "/apis/apps/v1/namespaces/"
            + workload["metadata"]["namespace"]
            + "/deployments/"
            + workload["metadata"]["name"]
        ] = workload
    appset = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {"name": "apps", "namespace": "argocd"},
        "spec": {
            "syncPolicy": {
                "applicationsSync": "sync",
                "preserveResourcesOnDeletion": True,
            }
        },
    }
    objects[PREFIX["ApplicationSet"] + "apps"] = appset
    objects["/apis/batch/v1/namespaces/selfhosted/jobs/restic-restore"] = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": "restic-restore", "namespace": "selfhosted"},
        "spec": {},
    }
    objects["/api/v1/namespaces/selfhosted/pods/stale"] = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "stale",
            "namespace": "selfhosted",
            "labels": {"job-name": "restic-restore"},
        },
    }
    objects["/api/v1/namespaces/selfhosted/pods/unrelated"] = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "unrelated",
            "namespace": "selfhosted",
            "labels": {"job-name": "different"},
        },
    }
    return {"objects": objects, "events": []}


def exported_plan(tmp_path):
    path = tmp_path / "plan.json"
    return path, [
        {
            "name": "Export observed plan",
            "ansible.builtin.copy": {
                "dest": str(path),
                "content": "{{ {'plan': restic_restore_plan, 'snapshot': restic_restore_effective_snapshot} | to_json }}",
                "mode": "0600",
            },
            "check_mode": False,
        }
    ]


@pytest.mark.parametrize(
    "mode,app,snapshot,check",
    [
        ("app", "paperless", "", False),
        ("all", "", "snapshot-selected", False),
        ("app", "missing", "latest", False),
        ("app", "missing-pvc", "latest", False),
        ("app", "gatus", "latest", False),
        ("app", "restic", "latest", False),
        ("app", "paperless", "latest", True),
    ],
)
def test_live_restore_planning(tmp_path, restore, mode, app, snapshot, check):
    path, after = exported_plan(tmp_path)
    if app == "missing-pvc":
        del restore["objects"][
            "/api/v1/namespaces/selfhosted/persistentvolumeclaims/paperless"
        ]
    if mode == "all":
        for obj in restore["objects"].values():
            if obj["kind"] == "PersistentVolumeClaim":
                obj["spec"]["storageClassName"] = "nfs-fast"
    with cluster_api(tmp_path, restore) as (connection, observed):
        result = run_role(
            tmp_path,
            "restic",
            "main",
            {
                **connection,
                "restic_restore_mode": mode,
                "restic_restore_app": "paperless" if app == "missing-pvc" else app,
                "restic_restore_confirm": check,
                "restic_restore_snapshot": snapshot,
            },
            check=check,
            after=after,
        )
        state = observed()
    valid = app not in ["missing", "missing-pvc", "gatus", "restic"]
    assert (result.returncode == 0) == valid, result.stdout + result.stderr
    assert all(event["method"] == "GET" for event in state["events"])
    if valid:
        plan = json.loads(path.read_text())
        assert plan["snapshot"] == (snapshot or "latest")
        assert {item["app"] for item in plan["plan"]} == (
            {"paperless"} if mode == "app" else {"paperless", "cert-data"}
        )
        paperless = next(item for item in plan["plan"] if item["app"] == "paperless")
        assert paperless["pvc_paths"] == ["/data/appdata/selfhosted/paperless"]
        assert paperless["restore_paths"] == [
            "/restore/data/appdata/selfhosted/paperless"
        ]
        assert {item["name"]: item["replicas"] for item in paperless["workloads"]} == {
            "paperless-main": 1,
            "paperless-gpt": 2,
        }
        assert (
            paperless["sync_policy"]
            == restore["objects"][PREFIX["Application"] + "paperless"]["spec"][
                "syncPolicy"
            ]
        )


@pytest.mark.parametrize(
    "failure,absent_policy",
    [
        ("", False),
        ("", True),
        ("prepare", False),
        ("restore", False),
        ("resume", False),
        ("cleanup", False),
        ("appset", False),
        ("ambiguous-appset", False),
        ("stale", False),
        ("stale-pod", False),
        ("stale-wait", False),
    ],
)
def test_restore_transaction_state_order_and_failure_evidence(
    tmp_path, restore, failure, absent_policy
):
    appset = PREFIX["ApplicationSet"] + "apps"
    if absent_policy:
        del restore["objects"][appset]["spec"]["syncPolicy"]
        del restore["objects"][PREFIX["Application"] + "paperless"]["spec"][
            "syncPolicy"
        ]
    if failure == "appset":
        del restore["objects"][appset]
    if failure == "ambiguous-appset":
        restore["duplicate_appset"] = True
    if failure in ["prepare", "resume"]:
        restore["failure"] = {
            "method": "PATCH",
            "path": "/deployments/paperless-main/scale",
            "replicas": 0 if failure == "prepare" else 1,
        }
    if failure in ["cleanup", "stale"]:
        restore["failure"] = {
            "method": "DELETE",
            "path": "/jobs/restic-restore",
            **({"after": "POST"} if failure == "cleanup" else {}),
        }
    if failure in ["stale-pod", "stale-wait"]:
        restore["failure"] = {
            "method": "DELETE" if failure == "stale-pod" else "GET",
            "path": "/pods/stale",
            **({"after": "DELETE"} if failure == "stale-wait" else {}),
        }
    collection = pod_exec_collection(tmp_path)
    with cluster_api(tmp_path, restore) as (connection, observed):
        result = run_role(
            tmp_path,
            "restic",
            "main",
            {
                **connection,
                "restic_restore_app": "paperless",
                "restic_restore_confirm": True,
                "restic_restore_snapshot": "selected-snapshot",
            },
            env={
                "ANSIBLE_COLLECTIONS_PATH": collection,
                "EXEC_STATE": str(tmp_path / "api-state.json"),
                "EXEC_FAIL": "restic" if failure == "restore" else "",
            },
        )
        state = observed()
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    assert "/api/v1/namespaces/selfhosted/pods/unrelated" in state["objects"]
    assert (
        state["objects"][
            "/apis/apps/v1/namespaces/platform-system/deployments/cert-data"
        ]["spec"]["replicas"]
        == 0
    )
    events = state["events"]
    app = PREFIX["Application"] + "paperless"
    app_patches = [
        (i, event)
        for i, event in enumerate(events)
        if event["method"] == "PATCH" and event["path"] == app
    ]
    pause = [
        i
        for i, event in app_patches
        if event["body"] == [{"op": "remove", "path": "/spec/syncPolicy/automated"}]
    ]
    destructive = [
        i
        for i, event in enumerate(events)
        if event["method"] == "EXEC"
        or (
            event["method"] == "PATCH"
            and event["path"].endswith("/scale")
            and event["body"].get("spec", {}).get("replicas") == 0
        )
    ]
    if absent_policy:
        assert not app_patches
        assert "syncPolicy" not in state["objects"][app]["spec"]
    elif destructive:
        assert len(pause) == 1 and pause[0] < min(destructive)
        appset_pause = next(
            i
            for i, event in enumerate(events)
            if event["method"] == "PATCH"
            and event["path"] == appset
            and event["body"]
            .get("spec", {})
            .get("syncPolicy", {})
            .get("applicationsSync")
            == "create-only"
        )
        assert appset_pause < pause[0]
        if failure in ["prepare", "restore", "resume"]:
            assert state["objects"][app]["spec"]["syncPolicy"] == {
                "retry": {"limit": 2}
            }
    for path, original in restore["objects"].items():
        if original["kind"] == "Application" and path != app:
            assert state["objects"][path] == original
    commands = [event["body"] for event in events if event["method"] == "EXEC"]
    if failure in ["appset", "ambiguous-appset"]:
        assert any(
            event["method"] == "GET" and event["path"] == appset for event in events
        )
        assert "ApplicationSet not found" in result.stdout
        assert not commands
    if fault := restore.get("failure"):
        candidates = [
            i
            for i, event in enumerate(events)
            if event["method"] == fault["method"]
            and fault["path"] in event["path"]
            and (
                fault.get("replicas") is None
                or event["body"].get("spec", {}).get("replicas") == fault["replicas"]
            )
        ]
        assert candidates, "injected failure never reached its intended native boundary"
        if fault.get("after"):
            assert any(
                event["method"] == fault["after"] for event in events[: candidates[-1]]
            )

    if not failure or failure in ["restore", "resume", "cleanup"]:
        assert commands[0].startswith("sh -ceu ")
        assert (
            "find '/restore/data/appdata/selfhosted/paperless' -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +"
            in commands[0]
        )
        assert (
            "restore selected-snapshot" in commands[1]
            and "--include /data/appdata/selfhosted/paperless" in commands[1]
        )
        defaults = read_yaml(ROOT / "ansible/roles/restic/defaults/main.yml")
        argv = shlex.split(commands[1])
        expected = {
            "--retry-lock": defaults["restic_restore_retry_lock"],
            "--host": defaults["restic_restore_snapshot_host"],
            "--tag": defaults["restic_restore_snapshot_tag"],
            "--path": defaults["restic_restore_snapshot_path"],
            "--target": defaults["restic_restore_target_root"],
            "--exclude-xattr": "*",
            "--include": "/data/appdata/selfhosted/paperless",
        }
        for flag, value in expected.items():
            assert argv.count(flag) == 1 and argv[argv.index(flag) + 1] == value
        delete_index = next(
            i for i, event in enumerate(events) if event["method"] == "EXEC"
        )
        paused = [
            event for event in events[:delete_index] if event["method"] == "PATCH"
        ]
        assert any(
            event["path"] == appset
            and event["body"]["spec"]["syncPolicy"]["applicationsSync"] == "create-only"
            for event in paused
        )
        assert {
            event["path"].rsplit("/", 2)[-2]
            for event in paused
            if event["path"].endswith("/scale")
            and event["body"]["spec"]["replicas"] == 0
        } == {"paperless-main", "paperless-gpt"}
    if not failure:
        assert (
            "/apis/batch/v1/namespaces/selfhosted/jobs/restic-restore"
            not in state["objects"]
        )
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
            ]["spec"]["replicas"]
            == 1
        )
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-gpt"
            ]["spec"]["replicas"]
            == 2
        )
        assert ("syncPolicy" in state["objects"][appset]["spec"]) == (not absent_policy)
        if not absent_policy:
            assert (
                state["objects"][appset]["spec"]["syncPolicy"]
                == restore["objects"][appset]["spec"]["syncPolicy"]
            )
            assert (
                state["objects"][PREFIX["Application"] + "paperless"]["spec"][
                    "syncPolicy"
                ]
                == restore["objects"][PREFIX["Application"] + "paperless"]["spec"][
                    "syncPolicy"
                ]
            )
    elif not failure.startswith("stale"):
        assert (
            "/apis/batch/v1/namespaces/selfhosted/jobs/restic-restore"
            in state["objects"]
        )
        assert "left for inspection" in result.stdout
        if failure == "resume":
            assert (
                state["objects"][
                    "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-gpt"
                ]["spec"]["replicas"]
                == 2
            )
            assert (
                state["objects"][
                    "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
                ]["spec"]["replicas"]
                == 0
            )
    else:
        assert not any(event["method"] == "POST" for event in events)


@pytest.mark.parametrize(
    "entry,check,path",
    [
        ("execute_prepare_app", False, "/"),
        ("execute_prepare_app", False, "/restore"),
        ("execute_prepare_app", False, "/restore/data/appdata"),
        ("execute_prepare_app", False, "/restore/data/appdata/selfhosted/paperless"),
        ("execute_prepare_app", True, "/restore/data/appdata/selfhosted/paperless"),
        ("execute_restore_app", True, "/restore/data/appdata/selfhosted/paperless"),
    ],
)
def test_direct_restore_exec_boundary_and_unsafe_roots(tmp_path, entry, check, path):
    variables = {
        "restic_restore_app_plan": {
            "had_automated_sync": False,
            "workloads": [],
            "restore_paths": [path],
            "pvc_paths": ["/data/appdata/selfhosted/paperless"],
        },
        "restic_restore_pod_name": "restore-pod",
        "restic_restore_effective_snapshot": "selected-snapshot",
    }
    with cluster_api(tmp_path, {"objects": {}, "events": []}) as (connection, observed):
        result = run_role(
            tmp_path,
            "restic",
            entry,
            {**connection, **variables},
            check=check,
            env={
                "ANSIBLE_COLLECTIONS_PATH": pod_exec_collection(tmp_path),
                "EXEC_STATE": str(tmp_path / "api-state.json"),
            },
        )
        events = observed()["events"]
    safe = path == "/restore/data/appdata/selfhosted/paperless"
    assert (result.returncode == 0) == safe, result.stdout + result.stderr
    assert bool(events) == (safe and not check)
    assert all(event["method"] == "EXEC" for event in events)


def test_real_pod_exec_module_loads_and_fails_at_connection_boundary(tmp_path):
    # A real collection/client import check keeps the websocket stub from hiding dependency breakage.
    variables = {
        "restic_restore_app_plan": {
            "pvc_paths": ["/data/appdata/selfhosted/paperless"]
        },
        "restic_restore_pod_name": "restore-pod",
        "restic_restore_effective_snapshot": "selected-snapshot",
    }
    with cluster_api(tmp_path, {"objects": {}, "events": []}) as (connection, observed):
        result = run_role(
            tmp_path, "restic", "execute_restore_app", {**connection, **variables}
        )
        events = observed()["events"]
    assert result.returncode != 0
    assert any(event["path"].endswith("/pods/restore-pod") for event in events), (
        result.stdout + result.stderr
    )
    assert "ImportError" not in result.stdout + result.stderr
