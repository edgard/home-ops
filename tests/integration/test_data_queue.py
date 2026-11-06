"""Actual role/API preflight and abort tests. No successful WebSocket exec is simulated."""

import json

from tests.integration.test_data_maintenance import (
    maintenance_api,
    obj,
    path_for,
    scenario_objects,
)
from tests.support.runtime import ROOT, run_role

ROLE = ROOT / "ansible/roles/shared_data"


def drain_scenario(grace=2000, env=None):
    app = obj(
        "Deployment",
        "paperless-main",
        "selfhosted",
        {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "paperless-main"}},
            "template": {
                "spec": {
                    "terminationGracePeriodSeconds": 2100,
                    "containers": [{"name": "app", "env": env or []}],
                }
            },
        },
    )
    pod = obj(
        "Pod",
        "paperless-main-old",
        "selfhosted",
        {
            "terminationGracePeriodSeconds": grace,
            "containers": [{"name": "app", "env": env or []}],
        },
    )
    pod["metadata"]["labels"] = {"app": "paperless-main"}
    pod["status"] = {"phase": "Pending"}
    registry = {
        "version": 1,
        "consumers": {
            "paperless": {
                "namespace": "selfhosted",
                "drain": {
                    "workload": "paperless-main",
                    "minimum_grace_seconds": 2000,
                    "required_env": {
                        "S6_SERVICES_GRACETIME": "2000000",
                        "S6_KILL_GRACETIME": "2000000",
                    },
                    "command": "python3 -c pass",
                    "inspect_command": "python3 -c pass",
                    "pause_command": "python3 -c pass",
                    "idle_command": "python3 -c pass",
                    "resume_command": "python3 -c pass",
                    "producer_workloads": [],
                },
            }
        },
    }
    return [app, pod], {
        "shared_data_drain_app": "paperless",
        "shared_data_apps": ["paperless"],
        "shared_data_registry": registry,
    }


def test_rejects_old_pod_even_after_template_grace_extended(tmp_path):
    objects, variables = drain_scenario(grace=30)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, str(ROLE), "drain_app", {**connection, **variables})
    assert result.returncode != 0
    assert "Live queue Pod lacks rehearsed shutdown protection" in result.stdout
    assert not any("/exec" in event["path"] for event in state["events"])


def test_rejects_actual_pod_s6_milliseconds_missing(tmp_path):
    objects, variables = drain_scenario(grace=2100)
    objects[0]["spec"]["template"]["spec"]["containers"][0]["env"] = [
        {"name": "S6_SERVICES_GRACETIME", "value": "2000000"},
        {"name": "S6_KILL_GRACETIME", "value": "2000000"},
    ]
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, str(ROLE), "drain_app", {**connection, **variables})
    assert result.returncode != 0
    assert "Live queue Pod lacks rehearsed shutdown protection" in result.stdout
    assert not any("/exec" in event["path"] for event in state["events"])


def test_records_pause_intent_even_when_no_queue_pod_exists(tmp_path):
    objects, variables = scenario_objects()
    variables["shared_data_drain_enabled"] = True
    variables["shared_data_registry"]["consumers"]["paperless"]["drain"] = {
        "workload": "paperless",
        "minimum_grace_seconds": 2000,
        "producer_workloads": [],
        "pause_command": "false",
        "idle_command": "false",
        "command": "false",
    }
    controller = next(
        row
        for row in objects
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "paperless"
    )
    controller["spec"]["template"] = {"spec": {"terminationGracePeriodSeconds": 2100}}
    # No queue Pods exists: intent must still be journaled before producer/worker controls.
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
    journal = json.loads(
        state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        ]["data"]["journal.json"]
    )
    assert journal["writers_touched"] is True
    assert "queue_pauses" in journal
    assert journal["queue_pauses"]["paperless"]["state"] in ["pause-intent", "paused"]


def journal_from(state):
    return json.loads(
        state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        ]["data"]["journal.json"]
    )


def queue_variables():
    objects, variables = scenario_objects()
    variables["shared_data_drain_enabled"] = True
    variables["shared_data_registry"]["consumers"]["paperless"]["drain"] = {
        "workload": "paperless",
        "minimum_grace_seconds": 2000,
        "producer_workloads": [],
        "pause_command": "false",
        "idle_command": "false",
        "resume_command": "false",
        "command": "false",
    }
    controller = next(
        row
        for row in objects
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "paperless"
    )
    controller["spec"]["template"] = {"spec": {"terminationGracePeriodSeconds": 2100}}
    return objects, variables


def inject_pause_intent(state, live_pod=False):
    pod = obj(
        "Pod",
        "paperless-original",
        "selfhosted",
        {"terminationGracePeriodSeconds": 2100, "containers": [{"name": "app"}]},
    )
    pod["metadata"]["labels"] = {"app": "paperless"}
    pod["status"] = {"phase": "Running"}
    if live_pod:
        state["objects"][path_for(pod)] = pod
    journal = journal_from(state)
    journal["writers_touched"] = True
    journal["queue_pauses"] = {
        "paperless": {
            "state": "pause-intent",
            "namespace": "selfhosted",
            "workload": "paperless",
            "pods": [
                {
                    "name": pod["metadata"]["name"],
                    "uid": pod["metadata"]["uid"],
                    "original": {
                        "services": {
                            "svc-webserver": "true true",
                            "svc-consumer": "true true",
                            "svc-scheduler": "true true",
                            "svc-worker": "true true",
                        },
                        "queues": ["celery"],
                        "hard_timeout_seconds": 1800,
                    },
                }
            ],
        }
    }
    state["objects"]["/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"][
        "data"
    ]["journal.json"] = json.dumps(journal)
    return pod


def test_failed_native_pause_api_keeps_intent_and_root_fence(tmp_path):
    objects, variables = queue_variables()
    with maintenance_api(tmp_path, objects) as (connection, state):
        prepared = run_role(
            tmp_path,
            str(ROLE),
            "maintenance_hold",
            {**connection, **variables, "shared_data_prepare_only": True},
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        inject_pause_intent(state, live_pod=True)
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        assert (
            journal_from(state)["queue_pauses"]["paperless"]["state"] == "pause-intent"
        )
        assert (
            not state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]["spec"]
            .get("syncPolicy", {})
            .get("automated")
        )
        assert any("/exec" in event["path"] for event in state["events"])


def test_interrupted_pause_restores_native_record_before_root_when_original_pod_gone(
    tmp_path,
):
    objects, variables = queue_variables()
    with maintenance_api(tmp_path, objects) as (connection, state):
        prepared = run_role(
            tmp_path,
            str(ROLE),
            "maintenance_hold",
            {**connection, **variables, "shared_data_prepare_only": True},
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        inject_pause_intent(state)
        state["events"].clear()
        result = run_role(
            tmp_path, str(ROLE), "maintenance_resume", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert journal_from(state)["queue_pauses"]["paperless"]["state"] == "resumed"
        assert journal_from(state)["phase"] == "complete"
        restored_native = []
        restored_root = []
        for index, event in enumerate(state["events"]):
            body = event.get("body", [])
            if event["method"] == "PATCH" and event["path"].endswith(
                "/configmaps/shared-data-operation"
            ):
                for row in body:
                    if (
                        row.get("path") == "/data/journal.json"
                        and json.loads(row["value"])
                        .get("queue_pauses", {})
                        .get("paperless", {})
                        .get("state")
                        == "resumed"
                    ):
                        restored_native.append(index)
            if (
                event["method"] == "PATCH"
                and event["path"].endswith("/applications/root")
                and any(
                    row.get("value", {}).get("automated")
                    for row in body
                    if isinstance(row.get("value"), dict)
                )
            ):
                restored_root.append(index)
        assert restored_native and restored_root
        assert min(restored_native) < min(restored_root)
        assert not any("/exec" in event["path"] for event in state["events"])


def test_unavailable_native_resume_never_unfences_root(tmp_path):
    objects, variables = queue_variables()
    with maintenance_api(tmp_path, objects) as (connection, state):
        prepared = run_role(
            tmp_path,
            str(ROLE),
            "maintenance_hold",
            {**connection, **variables, "shared_data_prepare_only": True},
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        inject_pause_intent(state, live_pod=True)
        result = run_role(
            tmp_path, str(ROLE), "maintenance_resume", {**connection, **variables}
        )
        assert result.returncode != 0
        assert journal_from(state)["phase"] != "complete"
        assert (
            not state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]["spec"]
            .get("syncPolicy", {})
            .get("automated")
        )


def test_failed_separate_producer_scale_retains_originals_and_pause_intent(tmp_path):
    objects, variables = queue_variables()
    producer = obj(
        "Deployment",
        "paperless-producer",
        "selfhosted",
        {"replicas": 1, "selector": {"matchLabels": {"app": "paperless-producer"}}},
    )
    objects.append(producer)
    variables["shared_data_registry"]["consumers"]["paperless"]["workloads"].append(
        {"kind": "Deployment", "name": "paperless-producer"}
    )
    variables["shared_data_registry"]["consumers"]["paperless"]["drain"][
        "producer_workloads"
    ] = ["paperless-producer"]
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["fail_scale_path"] = path_for(producer)
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        journal = journal_from(state)
        assert journal["queue_pauses"]["paperless"]["state"] == "pause-intent"
        assert state["objects"][path_for(producer)]["spec"]["replicas"] == 1
        original = next(
            row for row in journal["snapshots"] if row["name"] == "paperless-producer"
        )
        assert (
            original["field"] == "replicas"
            and original["present"]
            and original["value"] == 1
        )
        assert (
            not state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]["spec"]
            .get("syncPolicy", {})
            .get("automated")
        )


def test_terminating_original_pod_is_allowed_to_finish_before_resume(tmp_path):
    objects, variables = queue_variables()
    with maintenance_api(tmp_path, objects) as (connection, state):
        prepared = run_role(
            tmp_path,
            str(ROLE),
            "maintenance_hold",
            {**connection, **variables, "shared_data_prepare_only": True},
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        pod = inject_pause_intent(state, live_pod=True)
        state["objects"][path_for(pod)]["metadata"]["deletionTimestamp"] = (
            "2026-11-05T12:00:00Z"
        )
        reads = []

        def advance(path, state):
            if path == "/api/v1/namespaces/selfhosted/pods":
                reads.append(path)
                if len(reads) >= 3:
                    state["objects"][path_for(pod)]["status"]["phase"] = "Succeeded"

        state["on_get"] = advance
        state["events"].clear()
        result = run_role(
            tmp_path, str(ROLE), "maintenance_resume", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert journal_from(state)["phase"] == "complete"
        assert len(reads) >= 3
        pod_reads = [
            i
            for i, event in enumerate(state["events"])
            if event["path"] == "/api/v1/namespaces/selfhosted/pods"
        ]
        lease_renewals = [
            i
            for i, event in enumerate(state["events"])
            if event["method"] == "PATCH"
            and event["path"].endswith("/leases/shared-data-operation")
        ]
        assert all(
            any(left < renewal < right for renewal in lease_renewals)
            for left, right in zip(pod_reads, pod_reads[1:])
        )
        assert not any("/exec" in event["path"] for event in state["events"])


def test_required_native_queue_drain_cannot_be_disabled(tmp_path):
    objects, variables = queue_variables()
    variables["shared_data_drain_enabled"] = False
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        assert "Registered native queue draining cannot be bypassed" in result.stdout
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )


def test_expired_backup_pause_deadline_is_not_reset_by_queue_drain(tmp_path):
    objects, variables = queue_variables()
    variables["shared_data_capture_deadline"] = 0
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        assert "Native work remains active; abort capture" in result.stdout
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )


def test_prepare_only_resume_failure_never_stops_untouched_online_writers(tmp_path):
    objects, variables = queue_variables()
    with maintenance_api(tmp_path, objects) as (connection, state):
        prepared = run_role(
            tmp_path,
            str(ROLE),
            "maintenance_hold",
            {**connection, **variables, "shared_data_prepare_only": True},
        )
        assert prepared.returncode == 0, prepared.stdout + prepared.stderr
        state["events"].clear()
        state["fail_completion"] = True
        result = run_role(
            tmp_path, str(ROLE), "maintenance_resume", {**connection, **variables}
        )
        assert result.returncode != 0
        zeros = [
            event
            for event in state["events"]
            if event["method"] == "PATCH"
            and event["path"].endswith("/deployments/paperless")
            and any(
                row.get("path") == "/spec/replicas" and row.get("value") == 0
                for row in event.get("body", [])
            )
        ]
        assert zeros == []
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 2
        )
        assert journal_from(state)["phase"] == "resume-failed"
        assert (
            not state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]["spec"]
            .get("syncPolicy", {})
            .get("automated")
        )


def test_short_lease_cannot_cover_registered_queue_waits(tmp_path):
    objects, variables = drain_scenario(grace=2100)
    objects[1]["status"]["phase"] = "Succeeded"
    variables["shared_data_lease_duration"] = 300
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, str(ROLE), "drain_app", {**connection, **variables})
        assert result.returncode != 0
        assert "Native queue waits require at least a 900-second Lease" in result.stdout
        assert not any("/exec" in event["path"] for event in state["events"])
