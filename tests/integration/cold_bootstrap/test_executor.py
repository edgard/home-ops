"""Native role/API evidence for shared gate ownership and real executor fencing."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from tests.integration import test_data_maintenance as api
from tests.integration.cold_bootstrap.support import (
    IMAGE,
    REVISION,
    extend_api,
    git_boundary,
    infrastructure_objects,
    start_job_workers,
)
from tests.integration.cold_bootstrap.test_role import variables
from tests.support.runtime import load_module, run_role


def lease(operation="other", kind="restore"):
    actor = {
        "kind": "Pod",
        "name": "other",
        "namespace": "selfhosted",
        "uid": "other",
        "owners": [],
    }
    return {
        "apiVersion": "coordination.k8s.io/v1",
        "kind": "Lease",
        "metadata": {
            "name": "shared-data-operation",
            "namespace": "selfhosted",
            "uid": "lease",
            "resourceVersion": "1",
            "annotations": {
                "home-ops/data-coordinator": json.dumps(
                    {
                        "operation_id": operation,
                        "operation_kind": kind,
                        "actor": actor,
                        "stage": "journaled",
                    }
                )
            },
        },
        "spec": {
            "holderIdentity": operation + ":other",
            "leaseDurationSeconds": 900,
            "renewTime": "2026-01-01T00:00:00Z",
        },
    }


@pytest.mark.parametrize(
    "kind", ["restore", "provision", "upgrade", "backup", "node-operation"]
)
def test_competing_shared_lease_refuses_before_all_platform_mutations(
    tmp_path, monkeypatch, kind
):
    extend_api(monkeypatch)
    git_boundary(tmp_path)
    held = lease(kind=kind)
    if kind == "node-operation":
        record = json.loads(
            held["metadata"]["annotations"]["home-ops/data-coordinator"]
        )
        record["actor"]["kind"] = "NativeCLI"
        held["metadata"]["annotations"]["home-ops/data-coordinator"] = json.dumps(
            record
        )
        held["metadata"]["finalizers"] = ["home-ops/native-operation"]
    with api.maintenance_api(tmp_path, [held]) as (connection, state):
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            {**variables(connection), "platform_recovery_image": IMAGE},
            timeout=180,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert (
            "native CLI" if kind == "node-operation" else "competing"
        ) in result.stdout
        assert all(event["method"] == "GET" for event in state["events"])


def test_ordinary_data_actors_refuse_ambiguous_unfinished_cold_state(tmp_path):
    objects, params = api.scenario_objects()
    objects.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "shared-data-cold-recovery",
                "namespace": "selfhosted",
                "uid": "cold",
                "resourceVersion": "1",
            },
            "data": {"journal.json": json.dumps({"phase": "bootstrapping"})},
        }
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **params}
        )
        assert result.returncode != 0
        assert all(event["method"] == "GET" for event in state["events"])


def test_watchdog_refuses_cold_expiry_without_automatic_fencing_or_release(tmp_path):
    objects, params = api.scenario_objects()
    held = lease(kind="cold-bootstrap")
    objects.append(held)
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {**connection, **params, "shared_data_action": "watchdog"},
            after=[],
        )
        assert result.returncode != 0
        assert "cold or non-Pod executor" in result.stdout
        assert not any(
            event["method"] in {"POST", "PATCH", "DELETE"} for event in state["events"]
        )
        assert state["objects"][api.path_for(held)] == held


def test_concurrent_initializers_do_not_both_start_mutating_workers(
    tmp_path, monkeypatch
):
    extend_api(monkeypatch)
    paths = [tmp_path / "one", tmp_path / "two"]
    for path in paths:
        path.mkdir()
        git_boundary(path)
    with api.maintenance_api(tmp_path, infrastructure_objects()) as (connection, state):
        threads, workers = start_job_workers(
            tmp_path, connection, state, failure="helm"
        )

        def run(path):
            return run_role(
                path,
                "platform",
                "recovery_dispatch",
                {
                    **variables(connection),
                    "platform_recovery_image": IMAGE,
                    "platform_recovery_job_timeout": 600,
                },
                timeout=780,
            )

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, paths))
        for thread in threads:
            thread.join(timeout=10)
        [job] = [
            r
            for r in state["objects"].values()
            if r["kind"] == "Job" and not r["spec"].get("suspend")
        ]
        assert len(workers) == 1
        assert all(result.returncode != 0 for result in results)
        assert (
            len([event for event in state["events"] if event["method"] == "HELM"]) == 1
        )
        assert all(
            r["spec"]["replicas"] == 0
            for r in state["objects"].values()
            if r["kind"] == "Deployment"
            and r["metadata"]["name"].startswith("paperless")
        )
        saved = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-cold-recovery"
            ]["data"]["journal.json"]
        )
        assert saved["executor"]["job_uid"] == job["metadata"]["uid"]
        assert saved["phase"] == "bootstrapping"


def test_expired_old_executor_is_really_fenced_before_replacement_chart_work(
    tmp_path, monkeypatch
):
    extend_api(monkeypatch)
    bundle = git_boundary(tmp_path)
    executor = load_module("platform/filter_plugins/cold_executor.py")
    old_job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": "old-boot",
            "namespace": "platform-system",
            "uid": "old-job",
            "resourceVersion": "1",
        },
        "spec": {
            "suspend": False,
            "template": {
                "spec": {
                    "serviceAccountName": "old-boot",
                    "containers": [{"name": "bootstrap", "image": IMAGE}],
                }
            },
        },
        "status": {"active": 1},
    }
    old_pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "old-pod",
            "namespace": "platform-system",
            "uid": "old-pod",
            "resourceVersion": "1",
            "ownerReferences": [
                {
                    "kind": "Job",
                    "name": "old-boot",
                    "uid": "old-job",
                    "controller": True,
                }
            ],
        },
        "spec": deepcopy(old_job["spec"]["template"]["spec"]),
        "status": {"phase": "Running"},
    }
    old_pod["spec"]["nodeName"] = "node"
    context = {
        "apps": ["paperless"],
        "revision": REVISION,
        "source_sha256": bundle["source_sha256"],
        "image": IMAGE,
        "code_sha256": bundle["code_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
    }
    held = lease()
    held["spec"] = {}
    import jsonpatch

    held = jsonpatch.apply_patch(
        held,
        executor.cold_lease_patch(
            held,
            "",
            "recovery-test",
            {
                "kind": "Pod",
                "name": "old-pod",
                "namespace": "platform-system",
                "uid": "old-pod",
                "owners": old_pod["metadata"]["ownerReferences"],
                "fence_nodes": [{"name": "node", "uid": "node"}],
            },
            context,
            0,
        ),
    )
    journal = {
        "version": 1,
        "phase": "bootstrapping",
        "apps": ["paperless"],
        "revision": REVISION,
        "operation": "recovery-test",
        "source_sha256": bundle["source_sha256"],
        "token": "c" * 32,
        "inventory": [],
        "executor": {
            "job_name": "old-boot",
            "job_uid": "old-job",
            "namespace": "platform-system",
            "image": IMAGE,
            "code_sha256": bundle["code_sha256"],
            "bundle_sha256": bundle["bundle_sha256"],
            "artifacts": [],
        },
    }
    cm = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "shared-data-cold-recovery",
            "namespace": "selfhosted",
            "uid": "cold",
            "resourceVersion": "1",
        },
        "data": {"journal.json": json.dumps(journal)},
    }
    with api.maintenance_api(
        tmp_path, [*infrastructure_objects(), held, old_job, old_pod, cm]
    ) as (connection, state):
        threads, workers = start_job_workers(
            tmp_path, connection, state, failure="helm"
        )
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            {
                **variables(connection),
                "platform_recovery_image": IMAGE,
                "platform_recovery_fence_requested": True,
                "platform_recovery_job_timeout": 600,
            },
            timeout=780,
        )
        for thread in threads:
            thread.join(timeout=10)
        assert result.returncode != 0
        assert len(workers) == 1, result.stdout[-18000:] + result.stderr
        chart = [i for i, e in enumerate(state["events"]) if e["method"] == "HELM"]
        assert len(chart) == 1
        deleted = {
            e["path"] for e in state["events"][: chart[0]] if e["method"] == "DELETE"
        }
        assert api.path_for(old_job) in deleted and api.path_for(old_pod) in deleted
        assert (
            api.path_for(old_job) not in state["objects"]
            and api.path_for(old_pod) not in state["objects"]
        )
        assert state["objects"][api.path_for(held)]["spec"][
            "holderIdentity"
        ].startswith("recovery-test:pod-")


def test_placeholder_pod_identity_with_admin_credentials_cannot_bootstrap(
    tmp_path, monkeypatch
):
    extend_api(monkeypatch)
    git_boundary(tmp_path)
    with api.maintenance_api(tmp_path, infrastructure_objects()) as (connection, state):
        threads, workers = start_job_workers(
            tmp_path, connection, state, admin_worker=True
        )
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            {
                **variables(connection),
                "platform_recovery_image": IMAGE,
                "platform_recovery_job_timeout": 180,
            },
            timeout=300,
        )
        for thread in threads:
            thread.join(timeout=10)
        assert result.returncode != 0
        assert len(workers) == 1
        diagnostic = "".join(
            p.read_text() for p in tmp_path.glob("worker-*/result.log")
        )
        assert "authenticated bound Pod token" in diagnostic, diagnostic
        assert not any(event["method"] == "HELM" for event in state["events"])
        assert not any(r["kind"] == "Application" for r in state["objects"].values())
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-cold-recovery"
            ]["data"]["journal.json"]
        )
        assert journal["phase"] == "bootstrap-claimed"


def test_changed_lease_decision_cannot_be_claimed_after_suspended_job_creation(
    tmp_path, monkeypatch
):
    extend_api(monkeypatch)
    git_boundary(tmp_path)
    held = lease()
    held["metadata"]["annotations"] = {}
    held["spec"] = {}
    with api.maintenance_api(tmp_path, [*infrastructure_objects(), held]) as (
        connection,
        state,
    ):

        def renew(resource, state):
            if resource["kind"] == "Job":
                current = state["objects"][api.path_for(held)]
                current["metadata"]["resourceVersion"] = "2"
                current["spec"] = {"holderIdentity": "other:new-actor"}

        state["created"] = renew
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            {**variables(connection), "platform_recovery_image": IMAGE},
            timeout=180,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "Refuse a renewed or changed old ownership decision" in result.stdout
        assert (
            state["objects"][api.path_for(held)]["spec"]["holderIdentity"]
            == "other:new-actor"
        )
        mutations = [
            e
            for e in state["events"]
            if e["method"] in {"POST", "PATCH", "DELETE", "HELM"}
        ]
        assert mutations
        assert all(
            e.get("body", {}).get("kind") in {"Namespace", "Job"} for e in mutations
        )
        assert all(
            e.get("body", {}).get("spec", {}).get("suspend") is True
            for e in mutations
            if e.get("body", {}).get("kind") == "Job"
        )


@pytest.mark.parametrize("node_claim_failure", ["replacement", "name", "missing"])
def test_initial_node_claim_refuses_before_pod_cas_or_platform_writes(
    tmp_path, monkeypatch, node_claim_failure
):
    extend_api(monkeypatch)
    git_boundary(tmp_path)
    with api.maintenance_api(tmp_path, infrastructure_objects()) as (connection, state):
        threads, workers = start_job_workers(
            tmp_path,
            connection,
            state,
            failure="helm",
            node_claim_failure=node_claim_failure,
        )
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            {
                **variables(connection),
                "platform_recovery_image": IMAGE,
                "platform_recovery_job_timeout": 180,
            },
            timeout=300,
        )
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        assert result.returncode != 0, result.stdout + result.stderr
        assert len(workers) == 1
        held = state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]
        entry = json.loads(held["metadata"]["annotations"]["home-ops/data-coordinator"])
        assert entry["actor"]["kind"] == "Job", (
            "worker claimed Pod ownership before verifying signed original-node identity"
        )
        for event in state["events"]:
            if event["method"] == "PATCH" and event["path"] == api.path_for(held):
                for operation in event["body"]:
                    if operation["path"] == "/metadata/annotations":
                        claim = json.loads(
                            operation["value"]["home-ops/data-coordinator"]
                        )
                        assert claim["actor"]["kind"] == "Job"
        cm = state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-cold-recovery"
        ]
        [original] = state["worker_start_journals"].values()
        assert cm["data"]["journal.json"] == original
        [started_at] = state["worker_start_events"].values()
        assert all(
            event["method"] in {"GET", "IDENTITY"}
            for event in state["events"][started_at:]
        ), (
            "persisted API mutation after worker entry without authenticated original-node equality"
        )
        journal = json.loads(original)
        assert journal["phase"] == "bootstrap-claimed"
        assert not journal["executor"].get("pod_uid")
        assert not journal["executor"].get("node")
        assert not any(event["method"] == "HELM" for event in state["events"])
        assert not any(
            resource["kind"] == "Application" for resource in state["objects"].values()
        )
        diagnostic = "".join(
            p.read_text() for p in tmp_path.glob("worker-*/result.log")
        )
        assert "authenticated original node" in diagnostic, diagnostic
