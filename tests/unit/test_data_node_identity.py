"""Authenticated historical node identity cannot be inferred from current names."""

import json
from copy import deepcopy

import pytest

from tests.support.runtime import load_module
from tests.unit.test_data_fencing import state

m = load_module("shared_data/filter_plugins/maintenance.py")


def identity():
    pod = {
        "metadata": {
            "name": "actor",
            "namespace": "selfhosted",
            "uid": "pod-uid",
            "ownerReferences": [],
        },
        "spec": {"nodeName": "node", "serviceAccountName": "shared-data"},
        "status": {"phase": "Running"},
    }
    sa = {
        "metadata": {"name": "shared-data", "namespace": "selfhosted", "uid": "sa-uid"}
    }
    node = {
        "metadata": {"name": "node", "uid": "original"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    ssr = {
        "status": {
            "userInfo": {
                "uid": "sa-uid",
                "username": "system:serviceaccount:selfhosted:shared-data",
                "extra": {
                    "authentication.kubernetes.io/" + key: [value]
                    for key, value in {
                        "pod-name": "actor",
                        "pod-uid": "pod-uid",
                        "node-name": "node",
                        "node-uid": "original",
                    }.items()
                },
            }
        }
    }
    return pod, node, sa, ssr


def test_authenticated_original_identity_is_captured():
    pod, node, sa, ssr = identity()
    actor = m.shared_data_executor_actor(pod, node, sa, ssr)
    assert actor["fence_nodes"] == [{"name": "node", "uid": "original"}]


@pytest.mark.parametrize(
    "case",
    [
        "replacement",
        "missing",
        "blank",
        "ambiguous",
        "malformed",
        "wrong-pod",
        "wrong-sa",
        "wrong-name",
        "unready",
    ],
)
def test_initial_authenticated_node_identity_refuses_ambiguity(case):
    pod, node, sa, ssr = identity()
    user = ssr["status"]["userInfo"]
    extra = user["extra"]
    if case == "replacement":
        node["metadata"]["uid"] = "replacement"
    if case == "missing":
        extra.pop("authentication.kubernetes.io/node-uid")
    if case == "blank":
        extra["authentication.kubernetes.io/node-uid"] = [""]
    if case == "ambiguous":
        extra["authentication.kubernetes.io/node-uid"] = ["original", "replacement"]
    if case == "malformed":
        extra["authentication.kubernetes.io/node-uid"] = "original"
    if case == "wrong-pod":
        extra["authentication.kubernetes.io/pod-uid"] = ["other"]
    if case == "wrong-sa":
        user["uid"] = "other"
    if case == "wrong-name":
        extra["authentication.kubernetes.io/node-name"] = ["other"]
    if case == "unready":
        node["status"]["conditions"][0]["status"] = "Unknown"
    with pytest.raises(ValueError):
        m.shared_data_executor_actor(pod, node, sa, ssr)


@pytest.mark.parametrize(
    "case", ["replacement", "lost", "legacy", "child", "lost-child"]
)
def test_historical_identity_required_before_any_fencing(case):
    journal, lease, pods, jobs, nodes = state()
    actor = journal["holder"]
    actor["fence_nodes"] = [{"name": "node", "uid": "original"}]
    nodes[0]["metadata"]["uid"] = "original"
    record = json.loads(lease["metadata"]["annotations"][m._LEASE_RECORD])
    record["actor"] = deepcopy(actor)
    if case == "replacement":
        nodes[0]["metadata"]["uid"] = "replacement"
    if case == "lost":
        nodes = []
    if case == "legacy":
        actor.pop("fence_nodes")
        record["actor"].pop("fence_nodes")
    if case == "child":
        child = deepcopy(pods[0])
        child["metadata"]["uid"] = "child"
        child["metadata"]["name"] = "child"
        pods.append(child)
    if case == "lost-child":
        journal["upload_job"] = {
            "uid": "upload",
            "name": "upload",
            "namespace": "selfhosted",
        }
    lease["metadata"]["annotations"][m._LEASE_RECORD] = json.dumps(record)
    with pytest.raises(ValueError):
        m.shared_data_watchdog_fence(
            journal, lease, pods, jobs, nodes, 1_000_000_000, "watchdog"
        )


def test_absence_barrier_rechecks_original_uid():
    journal, lease, pods, jobs, nodes = state()
    journal["holder"]["fence_nodes"] = [{"name": "node", "uid": "original"}]
    record = json.loads(lease["metadata"]["annotations"][m._LEASE_RECORD])
    record["actor"] = deepcopy(journal["holder"])
    lease["metadata"]["annotations"][m._LEASE_RECORD] = json.dumps(record)
    nodes[0]["metadata"]["uid"] = "original"
    plan = m.shared_data_watchdog_fence(
        journal, lease, pods, jobs, nodes, 1_000_000_000, "watchdog"
    )
    assert m.shared_data_fence_complete(plan, [], [], nodes, "watchdog")
    nodes[0]["metadata"]["uid"] = "replacement"
    assert not m.shared_data_fence_complete(plan, [], [], nodes, "watchdog")
