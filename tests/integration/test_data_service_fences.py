"""Production registry maintenance keeps native servers running behind Argo holds."""

import json
from copy import deepcopy

import pytest

from tests.integration.test_data_maintenance import maintenance_api, obj, path_for
from tests.support.runtime import ROOT, load_module, run_role
from tests.support.sources import read_yaml

ENGINES = {"postgresql", "redis"}
JOURNAL = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
LEASE = (
    "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
)
ROOT_APP = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"


def production_scenario():
    registry = read_yaml(ROOT / "ansible/roles/shared_data/files/registry.yaml")
    filters = load_module("shared_data/filter_plugins/maintenance.py")
    targets = filters.shared_data_targets(
        registry, ["bazarr"], "service-hold", "backup"
    )
    policy = {"automated": {"selfHeal": True, "prune": True}, "retry": {"limit": 2}}
    objects = []
    for target in targets:
        role = target["role"]
        spec = (
            {"syncPolicy": deepcopy(policy)}
            if role in {"root", "application"}
            else {"syncPolicy": {"preserveResourcesOnDeletion": True}}
            if role == "appset"
            else {"suspend": False}
            if role == "cronjob"
            else {"replicas": 1, "selector": {"matchLabels": {"app": target["name"]}}}
        )
        objects.append(obj(target["kind"], target["name"], target["namespace"], spec))
    # Installed shared services are prerequisites, independently of planner output.
    for engine in sorted(ENGINES):
        if not any(
            row["kind"] == "Application" and row["metadata"]["name"] == engine
            for row in objects
        ):
            objects.append(
                obj("Application", engine, "argocd", {"syncPolicy": deepcopy(policy)})
            )
        application = next(
            row
            for row in objects
            if row["kind"] == "Application" and row["metadata"]["name"] == engine
        )
        application["metadata"]["uid"] = "installed-" + engine + "-application"
        if engine == "postgresql":
            application["metadata"]["annotations"] = {
                "argocd.argoproj.io/skip-reconcile": "false",
                "unrelated": "retain",
            }
        if engine == "redis":
            application["spec"].pop("syncPolicy")
        controller = obj(
            "Deployment",
            engine + "-main",
            "platform-system",
            {"replicas": 1, "selector": {"matchLabels": {"app": engine}}},
        )
        controller["status"] = {"replicas": 1, "readyReplicas": 1}
        pod = obj("Pod", engine + "-server", "platform-system")
        pod["metadata"]["labels"] = {"app": engine}
        pod["status"] = {"phase": "Running"}
        objects.extend([controller, pod])
    coordinator = obj("Pod", "coordinator", "selfhosted")
    coordinator["status"] = {"phase": "Running"}
    objects.append(coordinator)
    variables = {
        "shared_data_confirm": True,
        "shared_data_apps": ["bazarr"],
        "shared_data_operation_id": "service-hold",
        "shared_data_operation_kind": "backup",
        "shared_data_holder_pod_name": "coordinator",
        "shared_data_holder_pod_namespace": "selfhosted",
        "shared_data_holder_pod_uid": "coordinator-uid",
        "shared_data_wait_retries": 1,
        "shared_data_wait_delay": 0,
    }
    return objects, variables


def engine_app_paths(objects):
    return {
        path_for(row)
        for row in objects
        if row["kind"] == "Application" and row["metadata"]["name"] in ENGINES
    }


def assert_servers_untouched(state, originals):
    for path, original in originals.items():
        if original["metadata"].get("namespace") == "platform-system" and original[
            "metadata"
        ]["name"].startswith(("postgresql", "redis")):
            assert state["objects"][path] == original
            assert not any(
                event["path"] == path and event["method"] != "GET"
                for event in state["events"]
            )


def test_production_registry_binds_engines_drains_sync_and_resumes_root_last(tmp_path):
    objects, variables = production_scenario()
    originals = {path_for(row): deepcopy(row) for row in objects}
    paths = engine_app_paths(objects) | {ROOT_APP}
    for row in objects:
        if path_for(row) in paths:
            row["status"] = {"operationState": {"phase": "Running"}}
    with maintenance_api(tmp_path, objects) as (connection, state):

        def finish_sync_after_fence(path, current):
            row = current["objects"].get(path, {})
            if (
                path in paths
                and "automated" not in row.get("spec", {}).get("syncPolicy", {})
                and row.get("metadata", {})
                .get("annotations", {})
                .get("argocd.argoproj.io/skip-reconcile")
                != "true"
            ):
                reads = current.setdefault("engine_sync_reads", {})
                reads[path] = reads.get(path, 0) + 1
                if reads[path] >= 2:
                    row["status"] = {"operationState": {"phase": "Succeeded"}}

        state["on_get"] = finish_sync_after_fence
        held = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        assert held.returncode == 0, held.stdout + held.stderr
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        snapshots = {
            row["name"]: row
            for row in journal["snapshots"]
            if row["role"] == "application"
        }
        assert ENGINES <= snapshots.keys()
        assert journal["holder"]["fence_nodes"] == [{"name": "node", "uid": "node-uid"}]
        for engine in ENGINES:
            assert snapshots[engine]["uid"] == "installed-" + engine + "-application"
        for path in paths:
            assert "automated" not in state["objects"][path]["spec"]["syncPolicy"]
            assert state["engine_sync_reads"][path] >= 2
            assert (
                state["objects"][path]["metadata"]["annotations"][
                    "argocd.argoproj.io/skip-reconcile"
                ]
                == "true"
            )
        assert_servers_untouched(state, originals)
        boundary = len(state["events"])
        resumed = run_role(
            tmp_path, "shared_data", "maintenance_resume", {**connection, **variables}
        )
        assert resumed.returncode == 0, resumed.stdout + resumed.stderr
        for path, original in originals.items():
            assert state["objects"][path]["spec"] == original["spec"]
            assert state["objects"][path]["metadata"].get("annotations") == original[
                "metadata"
            ].get("annotations")
        patches = [
            event
            for event in state["events"][boundary:]
            if event["method"] == "PATCH" and event["path"] in originals
        ]
        assert patches[-1]["path"] == ROOT_APP
        assert (
            json.loads(state["objects"][JOURNAL]["data"]["journal.json"])["phase"]
            == "complete"
        )
        assert state["objects"][LEASE]["spec"]["holderIdentity"] == ""
        assert_servers_untouched(state, originals)


@pytest.mark.parametrize(
    "failure", ["inflight", "missing", "replaced", "queued", "skipped-running"]
)
def test_engine_sync_or_identity_failure_keeps_ownership_and_root_held(
    tmp_path, failure
):
    objects, variables = production_scenario()
    originals = {path_for(row): deepcopy(row) for row in objects}
    pg = next(
        path for path in engine_app_paths(objects) if path.endswith("/postgresql")
    )
    if failure in {"inflight", "skipped-running"}:
        next(row for row in objects if path_for(row) == pg)["status"] = {
            "operationState": {"phase": "Running"}
        }
    if failure == "skipped-running":
        next(row for row in objects if path_for(row) == pg)["metadata"]["annotations"][
            "argocd.argoproj.io/skip-reconcile"
        ] = "true"
    with maintenance_api(tmp_path, objects) as (connection, state):
        held = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        if failure in {"inflight", "skipped-running"}:
            assert held.returncode != 0, held.stdout + held.stderr
        else:
            assert held.returncode == 0, held.stdout + held.stderr
            if failure == "missing":
                state["objects"].pop(pg)
            elif failure == "queued":
                state["objects"][pg]["operation"] = {
                    "sync": {"revision": "unexpected-manual-sync"}
                }
            else:
                state["objects"][pg]["metadata"]["uid"] = "replacement-application"
            boundary = len(state["events"])
            resumed = run_role(
                tmp_path,
                "shared_data",
                "maintenance_resume",
                {**connection, **variables},
            )
            assert resumed.returncode != 0, resumed.stdout + resumed.stderr
            if failure == "queued":
                assert (
                    state["objects"][pg]["operation"]["sync"]["revision"]
                    == "unexpected-manual-sync"
                )
                assert not any(
                    event["method"] == "PATCH"
                    and isinstance(event.get("body"), list)
                    and any(
                        patch.get("path") == "/spec/replicas"
                        and patch.get("value", 0) > 0
                        for patch in event["body"]
                    )
                    for event in state["events"][boundary:]
                )
        assert (
            state["objects"][LEASE]["spec"]["holderIdentity"]
            == "service-hold:coordinator-uid"
        )
        assert "automated" not in state["objects"][ROOT_APP]["spec"]["syncPolicy"]
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        assert journal["phase"] != "complete"
        assert any(
            row["uid"] == "installed-postgresql-application"
            for row in journal["snapshots"]
        )
        assert_servers_untouched(state, originals)


def test_partial_resume_compensates_all_holds_after_foreign_engine_request(tmp_path):
    objects, variables = production_scenario()
    originals = {path_for(row): deepcopy(row) for row in objects}
    pg = next(
        path for path in engine_app_paths(objects) if path.endswith("/postgresql")
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        held = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        assert held.returncode == 0, held.stdout + held.stderr
        boundary = len(state["events"])

        def queue_after_redis_resume(path, value, current):
            if (
                path.endswith("/applications/redis")
                and value["metadata"]
                .get("annotations", {})
                .get("argocd.argoproj.io/skip-reconcile")
                != "true"
            ):
                current["objects"][pg]["operation"] = {
                    "sync": {"revision": "foreign-during-resume"}
                }
                current["objects"][pg]["metadata"]["resourceVersion"] = str(
                    int(current["objects"][pg]["metadata"]["resourceVersion"]) + 1
                )
                current["queued_after_redis_resume"] = True

        state["patched"] = queue_after_redis_resume
        resumed = run_role(
            tmp_path, "shared_data", "maintenance_resume", {**connection, **variables}
        )
        assert resumed.returncode != 0, resumed.stdout + resumed.stderr
        assert state.get("queued_after_redis_resume")
        assert state["objects"][pg]["operation"] == {
            "sync": {"revision": "foreign-during-resume"}
        }
        assert any(
            event["method"] == "PATCH"
            and isinstance(event.get("body"), list)
            and any(
                patch.get("path") == "/spec/replicas" and patch.get("value", 0) > 0
                for patch in event["body"]
            )
            for event in state["events"][boundary:]
        )
        for row in objects:
            current = state["objects"][path_for(row)]
            if row["kind"] == "Application":
                assert "automated" not in current["spec"].get("syncPolicy", {}), current
                assert (
                    current["metadata"]
                    .get("annotations", {})
                    .get("argocd.argoproj.io/skip-reconcile")
                    == "true"
                ), current
            elif row["kind"] == "ApplicationSet":
                assert (
                    current["spec"]["syncPolicy"]["applicationsSync"] == "create-only"
                )
            elif row["kind"] == "CronJob":
                assert current["spec"]["suspend"] is True
            elif row["kind"] == "Deployment" and row["metadata"]["name"] in {
                "bazarr",
                "tuppr",
            }:
                assert current["spec"]["replicas"] == 0
        journal = json.loads(state["objects"][JOURNAL]["data"]["journal.json"])
        assert journal["phase"] == "resume-failed"
        assert (
            state["objects"][LEASE]["spec"]["holderIdentity"]
            == "service-hold:coordinator-uid"
        )
        assert_servers_untouched(state, originals)
