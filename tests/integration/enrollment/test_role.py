"""Actual Ansible/Kubernetes modules against a synthetic local HTTP API."""

import json
from pathlib import Path

import pytest

from tests.support.runtime import ROOT
from tests.support.runtime import run_role as _run_role

from .api import maintenance_api, obj, path_for, scenario_objects

ROLE = ROOT / "ansible/roles/shared_data"


def run_role(directory, role, entry, variables):
    import yaml

    config = yaml.safe_load(Path(variables["kubeconfig_path"]).read_text())
    actor_context = "fixture-" + variables.get("shared_data_holder_pod_name", "")
    if any(context["name"] == actor_context for context in config["contexts"]):
        variables = {**variables, "kube_context": actor_context}
    result = _run_role(
        directory,
        role,
        entry,
        variables,
        env={
            "K8S_AUTH_KUBECONFIG": variables["kubeconfig_path"],
            "KUBECONFIG": variables["kubeconfig_path"],
            "K8S_AUTH_CONTEXT": variables.get("kube_context", "fixture"),
        },
        timeout=300,
    )
    (Path(directory) / (entry + "-result.log")).write_text(
        result.stdout + result.stderr
    )
    return result


def test_session_rejects_replacement_actor_without_any_write(tmp_path):
    assert (ROLE / "tasks/operator_actor.yml").is_file(), (
        "Missing immutable held actor prerequisite"
    )
    actor = obj(
        "Pod",
        "held-session",
        "selfhosted",
        {
            "containers": [{"name": "operations", "image": "image"}],
            "activeDeadlineSeconds": 21600,
            "restartPolicy": "Never",
        },
    )
    actor["status"] = {"phase": "Running"}
    actor["metadata"]["labels"] = {
        "home-ops/data-role": "operator",
        "home-ops/data-operation": "held-session",
    }
    with maintenance_api(tmp_path, [actor]) as (connection, state):
        result = run_role(
            tmp_path,
            str(ROLE),
            "operator_actor",
            {
                **connection,
                "shared_data_confirm": True,
                "shared_data_operation_id": "held-session",
                "shared_data_holder_pod_name": "held-session",
                "shared_data_holder_pod_uid": "replaced",
                "shared_data_image": "image",
            },
        )
    assert result.returncode != 0
    assert "live immutable standalone" in result.stdout
    assert not any(e["method"] != "GET" for e in state["events"])


def test_registered_source_change_blocks_old_resume_before_any_writer_restore(tmp_path):
    assert (ROLE / "tasks/enrollment_resume.yml").is_file()
    objects, variables = held_objects(state="held")
    variables["shared_data_enrollment_proof"]["desired_sha256"] = "changed-after-merge"
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "enrollment_resume", {**connection, **variables}
        )
    assert result.returncode != 0
    assert "Desired source changed" in result.stdout
    assert not positive_replica_events(state)
    assert not root_restored(state)


def held_objects(state="held"):

    import yaml

    from .test_enrollment import module, protected, template

    objects, variables = scenario_objects()
    registry = yaml.safe_load((ROLE / "files/registry.yaml").read_text())
    registry["maintenance"] = {}
    variables.update(
        shared_data_registry=registry,
        shared_data_operation_kind="migration",
        shared_data_operation_id="held-session",
        shared_data_holder_pod_name="held-session",
        shared_data_holder_pod_uid="held-session-uid",
        shared_data_image="image",
        shared_data_lease_duration=3600,
        shared_data_drain_enabled=True,
        shared_data_operator_step="apply",
    )
    # Use the real pinned native protection in the synthetic template.
    want = protected()
    want["spec"]["containers"][0]["image"] = registry["consumers"]["paperless"][
        "drain"
    ]["image"]
    before = template()
    before["spec"]["containers"][0]["image"] = want["spec"]["containers"][0][
        "image"
    ].split("@")[0]
    objects = [
        row
        for row in objects
        if row["metadata"]["name"] not in {"paperless", "coordinator", "export"}
        or row["kind"] == "Application"
    ]
    actor = obj(
        "Pod",
        "held-session",
        "selfhosted",
        {
            "containers": [{"name": "operations", "image": "image"}],
            "activeDeadlineSeconds": 21600,
            "restartPolicy": "Never",
        },
    )
    actor["metadata"]["labels"] = {
        "home-ops/data-role": "operator",
        "home-ops/data-operation": "held-session",
    }
    actor["status"] = {"phase": "Running"}
    main = obj(
        "Deployment",
        "paperless-main",
        "selfhosted",
        {
            "replicas": 0,
            "selector": {"matchLabels": {"app": "paperless-main"}},
            "template": before,
        },
    )
    gpt = obj(
        "Deployment",
        "paperless-gpt",
        "selfhosted",
        {"replicas": 0, "selector": {"matchLabels": {"app": "paperless-gpt"}}},
    )
    broker = obj(
        "Deployment",
        "paperless-redis",
        "selfhosted",
        {
            "replicas": 1,
            "template": {
                "spec": {"containers": [{"name": "app", "image": "private-redis"}]}
            },
        },
    )
    service = obj(
        "Service",
        "paperless-main",
        "selfhosted",
        {"selector": {"home-ops/enrollment-fence": "held-session"}},
    )
    objects += [actor, main, gpt, broker, service]
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "maintenance", ROLE / "filter_plugins/maintenance.py"
    )
    maintenance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maintenance)
    targets = maintenance.shared_data_targets(
        registry, ["paperless"], "held-session", "migration"
    )
    snapshots = []
    for target in targets:
        resource = next(
            row
            for row in objects
            if row["kind"] == target["kind"]
            and row["metadata"]["name"] == target["name"]
        )
        snapshot = maintenance.shared_data_snapshot(target, resource)
        if snapshot["role"] == "workload":
            snapshot["value"] = 1
        snapshots.append(snapshot)
    filters = module("enrollment")
    native = (ROLE / "files/paperless_enrollment.py").read_text().rstrip()
    import hashlib

    journal = {
        "version": 1,
        "operation_id": "held-session",
        "operation_kind": "migration",
        "apps": ["paperless"],
        "holder": {
            "uid": "held-session-uid",
            "name": "held-session",
            "namespace": "selfhosted",
            "owners": [],
            "kind": "Pod",
            "fence_nodes": [{"name": "node", "uid": "node-uid"}],
        },
        "phase": "held",
        "writers_touched": True,
        "recovery_result": "none",
        "snapshots": snapshots,
        "queue_pauses": {
            "paperless": {
                "state": "paused",
                "protocol": "paperless-enrollment-v1",
                "namespace": "selfhosted",
                "workload": "paperless-main",
                "pods": [
                    {
                        "name": "old-main",
                        "uid": "old-main-uid",
                        "original": {
                            "queues": ["celery"],
                            "hard_timeout_seconds": 1800,
                            "services": {
                                name: "true true"
                                for name in [
                                    "svc-consumer",
                                    "svc-scheduler",
                                    "svc-webserver",
                                    "svc-worker",
                                ]
                            },
                        },
                    }
                ],
            }
        },
        "enrollment": {
            "state": state,
            "source_revision": "a" * 40,
            "source_template_sha256": filters.digest(before),
            "controller_uid": main["metadata"]["uid"],
            "original_settings": filters.shared_data_enrollment_settings(before),
            "native_sha256": hashlib.sha256(native.encode()).hexdigest(),
            "resume_sha256": hashlib.sha256(
                registry["consumers"]["paperless"]["drain"]["resume_command"].encode()
            ).hexdigest(),
            "redis": {
                "uid": broker["metadata"]["uid"],
                "replicas": 1,
                "template_sha256": filters.digest(broker["spec"]["template"]),
            },
            "service": {
                "uid": service["metadata"]["uid"],
                "name": "paperless-main",
                "namespace": "selfhosted",
                "selector": {"app": "paperless-main"},
            },
        },
    }
    variables["shared_data_enrollment_proof"] = {
        "source_revision": "a" * 40,
        "target_revision": "b" * 40,
        "original_sha256": filters.digest(before),
        "desired_sha256": filters.digest(want),
        "source_template": before,
        "template": want,
        "registered_desired_verified": True,
    }
    cm = obj("ConfigMap", "shared-data-operation", "selfhosted")
    cm["data"] = {"journal.json": json.dumps(journal)}
    lease = obj(
        "Lease",
        "shared-data-operation",
        "selfhosted",
        {
            "holderIdentity": "held-session:held-session-uid",
            "renewTime": "2026-11-06T00:00:00Z",
            "leaseDurationSeconds": 3600,
            "leaseTransitions": 1,
        },
    )
    lease["metadata"]["annotations"] = {
        "home-ops/data-coordinator": json.dumps(
            {
                "operation_id": "held-session",
                "operation_kind": "migration",
                "actor": journal["holder"],
                "stage": "journaled",
            }
        )
    }
    objects += [cm, lease]
    return objects, variables


def positive_replica_events(state):
    return [
        event
        for event in state["events"]
        if event["method"] == "PATCH"
        and isinstance(event.get("body"), list)
        and any(
            row.get("path") == "/spec/replicas"
            and row.get("op") != "test"
            and row.get("value", 0) > 0
            for row in event["body"]
        )
    ]


def root_restored(state):
    return [
        event
        for event in state["events"]
        if event["method"] == "PATCH"
        and event["path"].endswith("/applications/root")
        and any(
            row.get("path") == "/spec/syncPolicy"
            and row.get("value", {}).get("automated")
            for row in event.get("body", [])
            if isinstance(row, dict)
        )
    ]


def test_exact_source_apply_remains_zero_and_survives_new_cli_same_actor(tmp_path):
    objects, variables = held_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "enrollment_apply", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["enrollment"]["state"] == "applied"
        assert journal["enrollment"]["target_revision"] == "b" * 40
        assert journal["holder"]["uid"] == "held-session-uid"
        result2 = run_role(
            tmp_path, str(ROLE), "enrollment_apply", {**connection, **variables}
        )
        assert result2.returncode == 0, result2.stdout + result2.stderr
    assert not positive_replica_events(state)
    assert not root_restored(state)
    assert not any(
        "paperless-redis" in e["path"] and e["method"] != "GET" for e in state["events"]
    )


def initial_objects():
    from copy import deepcopy

    objects, variables = held_objects()
    objects = [row for row in objects if row["kind"] not in {"Lease", "ConfigMap"}]
    for row in objects:
        if row["kind"] == "Deployment" and row["metadata"]["name"] in {
            "paperless-main",
            "paperless-gpt",
        }:
            row["spec"]["replicas"] = 1
        if row["kind"] == "Service":
            row["spec"]["selector"] = {"app": "paperless-main"}
    main = next(
        row
        for row in objects
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "paperless-main"
    )
    pod = obj(
        "Pod", "old-main", "selfhosted", deepcopy(main["spec"]["template"]["spec"])
    )
    pod["metadata"]["labels"] = {"app": "paperless-main"}
    pod["status"] = {"phase": "Running"}
    objects.append(pod)
    variables["shared_data_enrollment_budget"] = 30
    variables["shared_data_wait_delay"] = 1
    variables["shared_data_enrollment_proof"]["target_revision"] = "a" * 40
    variables["shared_data_enrollment_proof"]["template"] = deepcopy(
        variables["shared_data_enrollment_proof"]["source_template"]
    )
    variables["shared_data_enrollment_proof"]["desired_sha256"] = variables[
        "shared_data_enrollment_proof"
    ]["original_sha256"]
    variables["shared_data_operator_step"] = "enroll"
    return objects, variables


def native_reply(command, state):
    if command[-1] == "inspect" or "states={service:status" in " ".join(command):
        return 0, json.dumps(
            {
                "queues": ["celery"],
                "services": {
                    name: "true true"
                    for name in [
                        "svc-consumer",
                        "svc-scheduler",
                        "svc-webserver",
                        "svc-worker",
                    ]
                },
                "hard_timeout_seconds": 1800,
            }
        ) + "\n"
    if command[-1] == "pause":
        state["paused"] = True
        return (1, "") if state.get("fail_native_pause") else (0, "")
    if command[-1] == "idle":
        state["idle_polls"] = state.get("idle_polls", 0) + 1
        if state.get("busy") or state.get("http_busy"):
            return 1, ""
        state["native_idle"] = True
        return 0, ""
    if "add_consumer" in " ".join(command):
        state["native_resumed"] = True
        return 0, ""
    return 1, ""


def actual_pod_lifecycle(path, value, state):
    if path.endswith("/deployments/paperless-main"):
        if value["spec"]["replicas"] == 0:
            assert state.get("native_idle"), (
                "old main killed without native and HTTP idle"
            )
            state["objects"].pop("/api/v1/namespaces/selfhosted/pods/old-main", None)
        elif state.get("protected_start"):
            from copy import deepcopy

            pod = obj(
                "Pod",
                "new-main",
                "selfhosted",
                deepcopy(value["spec"]["template"]["spec"]),
            )
            pod["metadata"]["labels"] = {"app": "paperless-main"}
            pod["status"] = {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            }
            state["objects"][path_for(pod)] = pod


def test_real_role_native_pause_failure_retains_original_journal_and_old_main(tmp_path):
    objects, variables = initial_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        state.update(
            exec_reply=native_reply,
            fail_native_pause=True,
            patched=actual_pod_lifecycle,
        )
        result = run_role(
            tmp_path, str(ROLE), "enrollment", {**connection, **variables}
        )
        assert result.returncode != 0
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert "enrollment" in journal, result.stdout + result.stderr
        assert journal["enrollment"]["state"] == "pause-intent"
        assert state["paused"]
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
            ]["spec"]["replicas"]
            == 1
        )
        assert (
            state["objects"]["/api/v1/namespaces/selfhosted/pods/old-main"]["status"][
                "phase"
            ]
            == "Running"
        )
        # Explicit original-source abort recovers native dispatch and exact selector before root.
        variables["shared_data_operator_step"] = "abort"
        recovered = run_role(
            tmp_path, str(ROLE), "enrollment_resume", {**connection, **variables}
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        assert state["native_resumed"]
        assert state["objects"][
            "/api/v1/namespaces/selfhosted/services/paperless-main"
        ]["spec"]["selector"] == {"app": "paperless-main"}
        restores = root_restored(state)
        assert restores
        root_index = state["events"].index(restores[-1])
        native_index = max(
            index
            for index, event in enumerate(state["events"])
            if event["method"] == "EXEC"
        )
        assert native_index < root_index


def test_old_pod_http_activity_expiry_never_scales_main(tmp_path):
    objects, variables = initial_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        state.update(
            exec_reply=native_reply, http_busy=True, patched=actual_pod_lifecycle
        )
        result = run_role(
            tmp_path, str(ROLE), "enrollment", {**connection, **variables}
        )
        assert result.returncode != 0
        assert "Enrollment drain expired" in result.stdout, result.stdout
        assert state["idle_polls"] > 1
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
            ]["spec"]["replicas"]
            == 1
        )
    assert not root_restored(state)
    assert not any(event["method"] == "DELETE" for event in state["events"])


def test_full_hold_merge_apply_and_new_actual_pod_before_root_resume(tmp_path):
    objects, variables = initial_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        state.update(exec_reply=native_reply, patched=actual_pod_lifecycle)
        result = run_role(
            tmp_path, str(ROLE), "enrollment", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["enrollment"]["state"] == "held"
        assert journal["holder"]["uid"] == "held-session-uid"
        merge_index = len(state["events"])
        _, applied_vars = held_objects()
        variables["shared_data_enrollment_proof"] = applied_vars[
            "shared_data_enrollment_proof"
        ]
        result = run_role(
            tmp_path, str(ROLE), "enrollment_apply", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not positive_replica_events({"events": state["events"][merge_index:]})
        state["protected_start"] = True
        variables["shared_data_operator_step"] = "resume"
        result = run_role(
            tmp_path, str(ROLE), "enrollment_resume", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            state["objects"]["/api/v1/namespaces/selfhosted/pods/new-main"]["spec"][
                "terminationGracePeriodSeconds"
            ]
            == 2000
        )
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["phase"] == "complete"
        assert journal["holder"]["uid"] == "held-session-uid"
    root_index = state["events"].index(root_restored(state)[-1])
    readiness_reads = [
        i
        for i, e in enumerate(state["events"])
        if e["method"] == "GET" and e["path"].endswith("/pods") and i > merge_index
    ]
    assert readiness_reads and min(readiness_reads) < root_index
    assert not any(
        e["method"] != "GET" and "paperless-redis" in e["path"] for e in state["events"]
    )


def test_protected_apply_failure_retains_intent_zero_and_same_actor_retry(tmp_path):
    objects, variables = held_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["fail_template"] = True
        result = run_role(
            tmp_path, str(ROLE), "enrollment_apply", {**connection, **variables}
        )
        assert result.returncode != 0
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["enrollment"]["state"] == "apply-intent"
        assert journal["enrollment"]["target_revision"] == "b" * 40
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
            ]["spec"]["replicas"]
            == 0
        )
        assert not positive_replica_events(state)
        state["fail_template"] = False
        retried = run_role(
            tmp_path, str(ROLE), "enrollment_apply", {**connection, **variables}
        )
        assert retried.returncode == 0, retried.stdout + retried.stderr
    assert not root_restored(state)


def test_generic_resume_cannot_unfence_enrollment_without_source_validation(tmp_path):
    objects, variables = held_objects()
    journal = json.loads(
        next(row for row in objects if row["kind"] == "ConfigMap")["data"][
            "journal.json"
        ]
    )
    variables["shared_data_journal"] = journal
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, str(ROLE), "maintenance_restore", {**connection, **variables}
        )
        assert result.returncode != 0
        assert (
            "Enrollment requires explicit same-actor source verification"
            in result.stdout
        )
    assert not positive_replica_events(state)
    assert not root_restored(state)


def test_create_bounded_standalone_actor_and_refuse_name_reuse(tmp_path):
    image = "ghcr.io/edgard/home-ops-data-tools:" + "a" * 40 + "@sha256:" + "b" * 64
    variables = {
        "shared_data_confirm": True,
        "shared_data_operator_step": "create",
        "shared_data_operation_id": "held-session",
        "shared_data_operation_kind": "migration",
        "shared_data_image": image,
        "shared_data_apps": ["paperless"],
        "shared_data_lease_duration": 3600,
    }

    def created(value, _state):
        if value["kind"] == "Pod":
            value["status"] = {"phase": "Running"}

    with maintenance_api(tmp_path, []) as (connection, state):
        state["created"] = created
        result = run_role(tmp_path, str(ROLE), "operator", {**connection, **variables})
        assert result.returncode == 0, result.stdout + result.stderr
        pod = state["objects"]["/api/v1/namespaces/selfhosted/pods/held-session-unique"]
        assert pod["spec"]["activeDeadlineSeconds"] == 21600
        assert pod["spec"]["restartPolicy"] == "Never"
        assert pod["spec"]["securityContext"]["fsGroup"] == 1000
        assert not pod["metadata"].get("ownerReferences")
        assert pod["spec"]["containers"][0]["image"] == image
        assert not any(
            "secret" in row or "persistentVolumeClaim" in row
            for row in pod["spec"]["volumes"]
        )
        rerun = run_role(tmp_path, str(ROLE), "operator", {**connection, **variables})
        assert rerun.returncode != 0
    assert len([event for event in state["events"] if event["method"] == "POST"]) == 1


def interrupted_backup_objects(state="pause-intent"):
    objects, variables = held_objects(state=state)
    cm = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(cm["data"]["journal.json"])
    journal["operation_kind"] = "backup"
    lease = next(row for row in objects if row["kind"] == "Lease")
    record = json.loads(lease["metadata"]["annotations"]["home-ops/data-coordinator"])
    record["operation_kind"] = "backup"
    lease["metadata"]["annotations"]["home-ops/data-coordinator"] = json.dumps(record)
    cm["data"]["journal.json"] = json.dumps(journal)
    main = next(
        row
        for row in objects
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "paperless-main"
    )
    main["spec"]["replicas"] = 1
    pod = obj("Pod", "old-main", "selfhosted", main["spec"]["template"]["spec"])
    pod["metadata"]["labels"] = {"app": "paperless-main"}
    pod["status"] = {"phase": "Running"}
    objects.append(pod)
    import jsonpatch

    from tests.support.runtime import load_module

    maintenance = load_module("shared_data/filter_plugins/maintenance.py")
    variables["shared_data_registry"]["maintenance"] = {
        "applications": ["postgresql", "redis"]
    }
    for engine in ["postgresql", "redis"]:
        application = obj(
            "Application",
            engine,
            "argocd",
            {"syncPolicy": {"automated": {"selfHeal": True}}},
        )
        objects.append(application)
        journal["snapshots"].append(
            maintenance.shared_data_snapshot({"role": "application"}, application)
        )
    for snapshot in journal["snapshots"]:
        if snapshot["role"] in {"root", "application"}:
            application = next(
                row
                for row in objects
                if row["kind"] == "Application"
                and row["metadata"]["name"] == snapshot["name"]
            )
            held = jsonpatch.apply_patch(
                application, maintenance.shared_data_patch(snapshot, application)
            )
            held = jsonpatch.apply_patch(
                held, maintenance.shared_data_skip_patch(snapshot, held)
            )
            application.clear()
            application.update(held)
    cm["data"]["journal.json"] = json.dumps(journal)
    variables.update(
        shared_data_operation_kind="backup",
        shared_data_journal=journal,
        shared_data_executor=journal["holder"],
        shared_data_journal_resource_version=cm["metadata"]["resourceVersion"],
        shared_data_journal_uid=cm["metadata"]["uid"],
    )
    return objects, variables


def test_backup_recovery_restores_only_proven_native_state_and_keeps_root_held(
    tmp_path,
):
    objects, variables = interrupted_backup_objects()
    cm = next(row for row in objects if row["kind"] == "ConfigMap")
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["exec_reply"] = native_reply
        result = run_role(
            tmp_path, str(ROLE), "maintenance_restore", {**connection, **variables}
        )
        assert result.returncode != 0
        assert (
            "Enrollment requires explicit same-actor source verification"
            in result.stdout
        ), result.stdout + result.stderr
        assert state["native_resumed"]
        assert state["objects"][
            "/api/v1/namespaces/selfhosted/services/paperless-main"
        ]["spec"]["selector"] == {"app": "paperless-main"}
        journal = json.loads(state["objects"][path_for(cm)]["data"]["journal.json"])
        assert journal["phase"] == "enrollment-native-restored"
    assert not positive_replica_events(state)
    assert not root_restored(state)


def test_source_tcp_liveness_also_keeps_old_web_alive_until_idle(tmp_path):
    objects, variables = initial_objects()
    for row in objects:
        if row["kind"] == "Pod" and row["metadata"]["name"] == "old-main":
            row["spec"]["containers"][0]["livenessProbe"] = {
                "tcpSocket": {"port": 8000}
            }
        if row["kind"] == "Deployment" and row["metadata"]["name"] == "paperless-main":
            row["spec"]["template"]["spec"]["containers"][0]["livenessProbe"] = {
                "tcpSocket": {"port": 8000}
            }
    with maintenance_api(tmp_path, objects) as (connection, state):
        state.update(exec_reply=native_reply, patched=actual_pod_lifecycle)
        result = run_role(
            tmp_path, str(ROLE), "enrollment", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["native_idle"]
    assert not root_restored(state)


def test_prepare_refences_children_after_inflight_root_self_heal(tmp_path):
    objects, variables = initial_objects()
    variables["shared_data_prepare_only"] = True

    def on_get(path, state):
        prior_root_patch = any(
            e["method"] == "PATCH" and e["path"].endswith("/applications/root")
            for e in state["events"]
        )
        if (
            path.endswith("/applications/root")
            and prior_root_patch
            and not state.get("self_heal_injected")
        ):
            child = state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/paperless"
            ]
            child["spec"]["syncPolicy"]["automated"] = {"selfHeal": True, "prune": True}
            child["metadata"]["resourceVersion"] = str(
                int(child["metadata"]["resourceVersion"]) + 1
            )
            state["self_heal_injected"] = True

    with maintenance_api(tmp_path, objects) as (connection, state):
        state["on_get"] = on_get
        result = run_role(
            tmp_path, str(ROLE), "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["self_heal_injected"]
        for name in ["root", "paperless", "tuppr"]:
            resource = state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/" + name
            ]
            assert "automated" not in resource["spec"]["syncPolicy"]
        appset = state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applicationsets/apps"
        ]
        assert appset["spec"]["syncPolicy"]["applicationsSync"] == "create-only"
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless-main"
            ]["spec"]["replicas"]
            == 1
        )
        targets = [
            e
            for e in state["events"]
            if e["method"] == "PATCH"
            and any(
                part in e["path"]
                for part in ["/applications/", "/applicationsets/", "/deployments/"]
            )
        ]
        assert targets[0]["path"].endswith("/applications/root")


@pytest.mark.parametrize("enrollment_state", ["pause-intent", "draining"])
def test_interrupted_native_recovery_refuses_queued_engine_before_producers_or_route(
    tmp_path, enrollment_state
):
    objects, variables = interrupted_backup_objects(enrollment_state)
    engine = next(
        row
        for row in objects
        if row["kind"] == "Application" and row["metadata"]["name"] == "postgresql"
    )
    engine["operation"] = {"sync": {"revision": "foreign-during-native-pause"}}
    service = next(row for row in objects if row["kind"] == "Service")
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["exec_reply"] = native_reply
        result = run_role(
            tmp_path, str(ROLE), "maintenance_restore", {**connection, **variables}
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert not state.get("native_resumed")
        assert not any(event["method"] == "EXEC" for event in state["events"])
        assert state["objects"][path_for(service)]["spec"]["selector"] == {
            "home-ops/enrollment-fence": "held-session"
        }
        assert not any(
            event["method"] == "PATCH" and event["path"] == path_for(service)
            for event in state["events"]
        )
        assert state["objects"][path_for(engine)]["operation"] == {
            "sync": {"revision": "foreign-during-native-pause"}
        }
        assert not positive_replica_events(state)
        assert not root_restored(state)
