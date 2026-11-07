"""Exercise native SSR and actual role paths with independent token claims."""

import pytest

from tests.integration.test_data_maintenance import maintenance_api, scenario_objects
from tests.support.runtime import run_role


@pytest.mark.parametrize(
    "case", ["replacement", "missing", "ambiguous", "wrong-pod", "wrong-sa"]
)
def test_executor_refuses_unproven_original_node_before_claim(tmp_path, case):
    objects, variables = scenario_objects()
    with maintenance_api(tmp_path, objects) as (connection, state):
        user = state["token_identities"]["Bearer fixture-coordinator"]
        extra = user["extra"]
        if case == "replacement":
            state["objects"]["/api/v1/nodes/node"]["metadata"]["uid"] = "replacement"
        if case == "missing":
            extra.pop("authentication.kubernetes.io/node-uid")
        if case == "ambiguous":
            extra["authentication.kubernetes.io/node-uid"].append("replacement")
        if case == "wrong-pod":
            extra["authentication.kubernetes.io/pod-uid"] = ["other"]
        if case == "wrong-sa":
            user["uid"] = "other"
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_executor",
            {**connection, **variables},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": connection["kube_context"],
            },
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert all(row["method"] in {"GET", "IDENTITY"} for row in state["events"])


@pytest.mark.parametrize("case", ["replacement", "lost", "legacy", "child"])
def test_watchdog_refuses_historical_ambiguity_before_any_fencing_write(tmp_path, case):
    import json

    from tests.integration.test_data_coordination import held
    from tests.integration.test_data_maintenance import obj

    objects, variables, _ = held()
    if case == "replacement":
        next(row for row in objects if row["kind"] == "Node")["metadata"]["uid"] = (
            "replacement"
        )
    if case == "lost":
        # Keep another Ready node so the fixture does not create an absent one.
        node = next(row for row in objects if row["kind"] == "Node")
        node["metadata"]["name"] = "other"
        node["metadata"]["uid"] = "other"
        # Watchdog itself is correctly authenticated to the other node.
        next(
            row
            for row in objects
            if row["kind"] == "Pod" and row["metadata"]["name"] == "watchdog"
        )["spec"]["nodeName"] = "other"
    if case == "legacy":
        for row in objects:
            if row["kind"] == "Lease":
                record = json.loads(
                    row["metadata"]["annotations"]["home-ops/data-coordinator"]
                )
                record["actor"].pop("fence_nodes")
                row["metadata"]["annotations"]["home-ops/data-coordinator"] = (
                    json.dumps(record)
                )
            if row["kind"] == "ConfigMap":
                journal = json.loads(row["data"]["journal.json"])
                journal["holder"].pop("fence_nodes")
                journal["coordinator"].pop("fence_nodes")
                row["data"]["journal.json"] = json.dumps(journal)
    if case == "child":
        pod = obj("Pod", "unknown-child", "selfhosted")
        pod["metadata"]["ownerReferences"] = [{"kind": "Job", "uid": "capture-job-uid"}]
        pod["status"] = {"phase": "Succeeded"}
        objects.append(pod)
    with maintenance_api(tmp_path, objects) as (connection, state):
        before = {
            path: json.dumps(row, sort_keys=True)
            for path, row in state["objects"].items()
        }
        result = run_role(
            tmp_path,
            "shared_data",
            "watchdog",
            {**connection, **variables},
            timeout=240,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert before == {
            path: json.dumps(row, sort_keys=True)
            for path, row in state["objects"].items()
        }
        assert all(event["method"] in {"GET", "IDENTITY"} for event in state["events"])


def test_node_replacement_after_old_pod_deletion_cannot_resume_root(tmp_path):
    import json

    from tests.integration.test_data_coordination import held

    objects, variables, _ = held()
    with maintenance_api(tmp_path, objects) as (connection, state):
        old = "/api/v1/namespaces/selfhosted/pods/coordinator"

        def replace_at_barrier(path, current):
            if path == "/api/v1/nodes" and old not in current["objects"]:
                current["objects"]["/api/v1/nodes/node"]["metadata"]["uid"] = (
                    "replacement"
                )
                current["replaced_after_delete"] = True

        state["on_get"] = replace_at_barrier
        result = run_role(
            tmp_path,
            "shared_data",
            "watchdog",
            {**connection, **variables},
            timeout=240,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert state.get("replaced_after_delete")
        lease = state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]
        assert lease["spec"]["holderIdentity"] == "test-backup:watchdog-uid"
        record = json.loads(
            lease["metadata"]["annotations"]["home-ops/data-coordinator"]
        )
        assert record["fence_actors"][0]["fence_nodes"] == [
            {"name": "node", "uid": "node-uid"}
        ]
        root = state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        ]
        assert "automated" not in root["spec"]["syncPolicy"]


def test_watchdog_fences_unlabelled_upload_pod_after_its_job_disappears(tmp_path):
    import json

    from tests.integration.test_data_coordination import held
    from tests.integration.test_data_maintenance import obj, path_for

    objects, variables, _ = held()
    cm = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(cm["data"]["journal.json"])
    journal["upload_job"] = {
        "kind": "Job",
        "uid": "gone-upload-uid",
        "name": "gone-upload",
        "namespace": "selfhosted",
        "node_binding": "coordinator-assigned-before-start",
        "fence_nodes": [{"name": "node", "uid": "node-uid"}],
    }
    cm["data"]["journal.json"] = json.dumps(journal)
    child = obj("Pod", "orphan-upload", "selfhosted")
    child["metadata"]["ownerReferences"] = [{"kind": "Job", "uid": "gone-upload-uid"}]
    child["status"] = {"phase": "Running"}
    objects.append(child)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "watchdog",
            {**connection, **variables},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        deleted = next(
            index
            for index, event in enumerate(state["events"])
            if event["method"] == "DELETE" and event["path"] == path_for(child)
        )
        assert (
            state["events"][deleted]["body"]["preconditions"]["uid"]
            == child["metadata"]["uid"]
        )
        resumed = next(
            index
            for index, event in enumerate(state["events"])
            if event["method"] == "PATCH"
            and isinstance(event["body"], list)
            and any(
                row.get("path") == "/spec/replicas" and row.get("value", 0) > 0
                for row in event["body"]
            )
        )
        assert deleted < resumed
        assert path_for(child) not in state["objects"]
        lease = state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]
        assert lease["spec"]["holderIdentity"] == ""
