"""Real Ansible API-only watchdog, no production cluster or storage."""

import json
from copy import deepcopy

import jsonpatch

import tests.integration.test_data_maintenance as api
from tests.support.runtime import ROOT, load_module, run_role

filters = load_module("shared_data/filter_plugins/maintenance.py")


def held(kind="backup", expired=True):
    objects, v = api.scenario_objects()
    targets = filters.shared_data_targets(
        v["shared_data_registry"],
        v["shared_data_apps"],
        v["shared_data_operation_id"],
        kind,
    )
    original = {api.path_for(o): deepcopy(o) for o in objects}
    snapshots = []
    for target in targets:
        old = next(
            o
            for o in objects
            if o["kind"] == target["kind"]
            and o["metadata"]["name"] == target["name"]
            and o["metadata"]["namespace"] == target["namespace"]
        )
        snap = filters.shared_data_snapshot(target, old)
        snapshots.append(snap)
        new = jsonpatch.apply_patch(old, filters.shared_data_patch(snap, old))
        old.clear()
        old.update(new)
        if old["kind"] == "Deployment":
            old["status"] = {"replicas": 0, "readyReplicas": 0}
    actor = {
        "uid": "coordinator-uid",
        "name": "coordinator",
        "namespace": "selfhosted",
        "kind": "Pod",
        "fence_nodes": [{"name": "node", "uid": "node-uid"}],
        "owners": [
            {
                "uid": "capture-job-uid",
                "kind": "Job",
                "name": "capture-job",
                "apiVersion": "batch/v1",
            }
        ],
    }
    oldpod = next(o for o in objects if o["kind"] == "Pod")
    oldpod["metadata"]["ownerReferences"] = actor["owners"]
    oldpod["spec"]["nodeName"] = "node"
    job = api.obj("Job", "capture-job", "selfhosted")
    objects.append(job)
    watchdog = api.obj("Pod", "watchdog", "selfhosted")
    watchdog["status"] = {"phase": "Running"}
    watchdog["spec"]["nodeName"] = "node"
    objects.append(watchdog)
    node = api.obj("Node", "node", "unused")
    node["metadata"].pop("namespace")
    node["status"] = {"conditions": [{"type": "Ready", "status": "True"}]}
    objects.append(node)
    lease = api.obj("Lease", "shared-data-operation", "selfhosted")
    lease = jsonpatch.apply_patch(
        lease,
        filters.shared_data_lease_takeover(
            lease,
            "",
            v["shared_data_operation_id"],
            kind,
            actor,
            0 if expired else 9_999_999_999,
            900,
        ),
    )
    journal = {
        "version": 1,
        "operation_id": v["shared_data_operation_id"],
        "operation_kind": kind,
        "apps": v["shared_data_apps"],
        "holder": actor,
        "coordinator": actor,
        "epoch": 1,
        "phase": "held",
        "snapshots": snapshots,
        "recovery_result": "none",
    }
    cm = api.obj("ConfigMap", "shared-data-operation", "selfhosted")
    cm["data"] = {"journal.json": json.dumps(journal)}
    objects += [lease, cm]
    v.update(
        shared_data_holder_pod_name="watchdog",
        kube_context="fixture-watchdog",
        shared_data_holder_pod_uid="watchdog-uid",
        shared_data_operation_kind=kind,
        shared_data_fence_wait_timeout=1,
    )
    return objects, v, original


def run(tmp_path, objects, v, **state_changes):
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        state.update(state_changes)
        result = run_role(
            tmp_path,
            "shared_data",
            "watchdog",
            {**connection, **v},
            env={"ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
            timeout=240,
        )
        return result, state


def test_unexpired_watchdog_is_nonmutating_success(tmp_path):
    objects, v, _ = held(expired=False)
    result, state = run(tmp_path, objects, v)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not any(e["method"] not in {"GET", "IDENTITY"} for e in state["events"])


def test_stale_backup_fences_job_and_pod_before_resuming_root_last(tmp_path):
    objects, v, original = held()
    result, state = run(tmp_path, objects, v)
    assert result.returncode == 0, result.stdout + result.stderr
    events = state["events"]
    delete = next(i for i, e in enumerate(events) if e["method"] == "DELETE")
    restores = [
        i
        for i, e in enumerate(events)
        if e["method"] == "PATCH"
        and e["path"] in original
        and e["path"] != "/api/v1/namespaces/selfhosted/pods/coordinator"
    ]
    assert restores and min(restores) > delete
    assert (
        events[restores[-1]]["path"]
        == "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
    )
    assert events[delete]["body"]["preconditions"]["uid"] == "coordinator-uid"
    assert events[delete]["body"].get("gracePeriodSeconds") is None
    journal = json.loads(
        state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        ]["data"]["journal.json"]
    )
    assert journal["phase"] == "complete"
    assert not state["objects"][
        "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
    ]["spec"]["holderIdentity"]


def test_destructive_failure_is_fenced_but_writers_remain_held(tmp_path):
    objects, v, _ = held(kind="restore")
    result, state = run(tmp_path, objects, v)
    assert result.returncode != 0
    assert any(e["method"] == "DELETE" for e in state["events"])
    journal = json.loads(
        state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        ]["data"]["journal.json"]
    )
    assert journal["phase"] == "held"
    assert (
        state["objects"]["/apis/apps/v1/namespaces/selfhosted/deployments/paperless"][
            "spec"
        ]["replicas"]
        == 0
    )


def test_unhealthy_node_prevents_any_automatic_mutation(tmp_path):
    objects, v, _ = held()
    next(o for o in objects if o["kind"] == "Node")["status"]["conditions"][0][
        "status"
    ] = "Unknown"
    result, state = run(tmp_path, objects, v)
    assert result.returncode != 0
    assert not any(e["method"] not in {"GET", "IDENTITY"} for e in state["events"])


def test_nfs_hung_pod_never_causes_forced_delete_or_writer_resumption(tmp_path):
    objects, v, _ = held()
    result, state = run(tmp_path, objects, v, hang_pods=True)
    assert result.returncode != 0
    deletes = [e for e in state["events"] if e["method"] == "DELETE"]
    assert deletes and all(e["body"].get("gracePeriodSeconds") is None for e in deletes)
    assert (
        state["objects"]["/apis/apps/v1/namespaces/selfhosted/deployments/paperless"][
            "spec"
        ]["replicas"]
        == 0
    )
    journal = json.loads(
        state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        ]["data"]["journal.json"]
    )
    assert journal["phase"] == "held"


def test_prepare_fences_gitops_without_stopping_online_preseed_writers(tmp_path):
    objects, v = api.scenario_objects()
    roles = str(ROOT / "ansible/roles")
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **v, "shared_data_prepare_only": True},
            env={"ANSIBLE_ROLES_PATH": roles},
            timeout=240,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["phase"] == "prepared"
        assert not state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        ]["spec"]["syncPolicy"].get("automated")
        assert (
            state["objects"]["/apis/batch/v1/namespaces/selfhosted/cronjobs/export"][
                "spec"
            ]["suspend"]
            is True
        )
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **v, "shared_data_prepare_only": False},
            env={"ANSIBLE_ROLES_PATH": roles},
            timeout=240,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        final = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert final["phase"] == "held" and final["snapshots"] == journal["snapshots"]
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 0
        )


def test_scheduled_coordinator_fences_its_cron_without_waiting_for_itself(tmp_path):
    objects, v = api.scenario_objects()
    objects += [
        api.obj(
            "Application",
            name,
            "argocd",
            {"syncPolicy": {"automated": {"selfHeal": True}}},
        )
        for name in ["shared-data", "restic"]
    ]
    cron = api.obj("CronJob", "operation-schedule", "selfhosted")
    objects.append(cron)
    job = api.obj("Job", "operation-job", "selfhosted")
    job["metadata"]["ownerReferences"] = [
        {
            "kind": "CronJob",
            "name": cron["metadata"]["name"],
            "uid": cron["metadata"]["uid"],
            "apiVersion": "batch/v1",
        }
    ]
    objects.append(job)
    actor = next(o for o in objects if o["kind"] == "Pod")
    actor["metadata"]["ownerReferences"] = [
        {
            "kind": "Job",
            "name": job["metadata"]["name"],
            "uid": job["metadata"]["uid"],
            "apiVersion": "batch/v1",
        }
    ]
    v["shared_data_registry"]["maintenance"] = {
        "applications": ["shared-data", "restic"],
        "cronjobs": [{"namespace": "selfhosted", "name": "operation-schedule"}],
    }
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **v, "shared_data_prepare_only": True},
            env={"ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
            timeout=240,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["objects"][api.path_for(cron)]["spec"]["suspend"] is True
        assert state["objects"][api.path_for(job)]["spec"].get("suspend") is not True
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )


def test_backup_preview_never_claims_or_changes_cluster_state(tmp_path):
    objects, variables = api.scenario_objects()
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "backup",
                "shared_data_confirm": False,
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not state["events"]


def test_provision_preview_is_nonmutating(tmp_path):
    objects, variables = api.scenario_objects()
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "provision",
                "shared_data_confirm": False,
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not state["events"]


def test_restore_preview_is_nonmutating(tmp_path):
    objects, variables = api.scenario_objects()
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "restore",
                "shared_data_confirm": False,
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not state["events"]


def test_manual_uploader_blocks_new_operation_until_job_and_pod_are_terminal(tmp_path):
    objects, variables = api.scenario_objects()
    uploader = api.obj("Job", "previous-upload", "selfhosted")
    uploader["metadata"]["labels"] = {"home-ops/data-operation": "previous"}
    pod = api.obj("Pod", "previous-upload-pod", "selfhosted")
    pod["metadata"]["ownerReferences"] = [
        {
            "kind": "Job",
            "uid": uploader["metadata"]["uid"],
            "name": "previous-upload",
            "apiVersion": "batch/v1",
        }
    ]
    pod["status"] = {"phase": "Running"}
    objects += [uploader, pod]
    variables["shared_data_prepare_only"] = True
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )
        assert not any(event["method"] == "DELETE" for event in state["events"])
        state["objects"][api.path_for(uploader)]["status"] = {
            "conditions": [{"type": "Complete", "status": "True"}]
        }
        state["objects"][api.path_for(pod)]["status"]["phase"] = "Succeeded"
        result = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["phase"] == "prepared"


def test_job_submission_preview_is_nonmutating(tmp_path):
    objects, variables = api.scenario_objects()
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "submit",
                "shared_data_job_action": "backup",
                "shared_data_confirm": False,
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not state["events"]


def test_delayed_coordinator_refuses_changed_live_registry_before_mutation(tmp_path):
    import yaml

    objects, variables = api.scenario_objects()
    registry = api.obj("ConfigMap", "shared-data-registry", "selfhosted")
    registry["data"] = {
        "registry.yaml": yaml.safe_dump(
            {"version": 1, "consumers": {"different": {"enabled": False}}}
        )
    }
    objects.append(registry)
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "backup",
                "shared_data_require_current_registry": True,
            },
        )
        assert result.returncode != 0
        assert "registry differs" in result.stdout
        assert not any(event["method"] != "GET" for event in state["events"])


def test_full_restore_plan_includes_registered_files_and_sqlite_but_not_future_databases(
    tmp_path,
):
    objects, variables = api.scenario_objects()
    variables["shared_data_registry"]["consumers"].update(
        {
            "legacy": {"enabled": False, "backend": "sqlite"},
            "future": {"enabled": False, "backend": "postgresql"},
        }
    )
    variables["shared_data_registry"]["file_consumers"] = {
        "files": {"pvcs": ["selfhosted/files"]}
    }
    variables.update(
        shared_data_action="plan",
        shared_data_job_action="restore",
        shared_data_scope_all=True,
        shared_data_apps=[],
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {**connection, **variables},
            after=[
                {
                    "ansible.builtin.copy": {
                        "content": "{{ shared_data_selected_apps | to_json }}",
                        "dest": str(tmp_path / "scope.json"),
                        "mode": "0600",
                    }
                }
            ],
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert set(json.loads((tmp_path / "scope.json").read_text())) == {
            "paperless",
            "legacy",
            "files",
        }
        assert not state["events"]


def test_quiescence_iteration_renews_existing_operation_ownership(tmp_path):
    objects, variables, _ = held(expired=False)
    journal = json.loads(
        next(obj for obj in objects if obj["kind"] == "ConfigMap")["data"][
            "journal.json"
        ]
    )
    variables.update(
        shared_data_holder_pod_name="coordinator",
        kube_context="fixture-coordinator",
        shared_data_holder_pod_uid="coordinator-uid",
        shared_data_journal=journal,
        shared_data_wait_targets=[],
        shared_data_writer_attempt=0,
        shared_data_wait_retries=0,
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_executor",
            {**connection, **variables},
            after=[
                {
                    "ansible.builtin.include_role": {
                        "name": "shared_data",
                        "tasks_from": "maintenance_poll_writers",
                    }
                }
            ],
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        lease_renewals = [
            event
            for event in state["events"]
            if event["method"] == "PATCH"
            and "/leases/shared-data-operation" in event["path"]
        ]
        assert len(lease_renewals) == 1
        first_inventory = next(
            i
            for i, event in enumerate(state["events"])
            if event["path"].endswith("/jobs")
        )
        assert state["events"].index(lease_renewals[0]) < first_inventory
