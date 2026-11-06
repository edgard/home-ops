"""Stale work must be fenced by immutable identity and a healthy node."""

import json
from copy import deepcopy

import pytest

from tests.support.runtime import load_module

m = load_module("shared_data/filter_plugins/maintenance.py")


def state():
    actor = {
        "name": "capture-abc",
        "namespace": "selfhosted",
        "uid": "actor-uid",
        "owners": [{"uid": "job-uid", "kind": "Job"}],
    }
    journal = {
        "operation_id": "capture",
        "operation_kind": "backup",
        "holder": actor,
        "phase": "held",
    }
    record = {
        "operation_id": "capture",
        "operation_kind": "backup",
        "actor": actor,
        "stage": "journaled",
    }
    lease = {
        "metadata": {"annotations": {"home-ops/data-claim": json.dumps(record)}},
        "spec": {
            "holderIdentity": "capture:actor-uid",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    }
    # Use native annotation spelling rather than duplicate that contract here.
    lease["metadata"]["annotations"] = {m._LEASE_RECORD: json.dumps(record)}
    pod = {
        "kind": "Pod",
        "metadata": {
            "name": "capture-abc",
            "namespace": "selfhosted",
            "uid": "actor-uid",
            "resourceVersion": "1",
            "ownerReferences": [{"kind": "Job", "uid": "job-uid"}],
        },
        "spec": {"nodeName": "node"},
        "status": {"phase": "Running"},
    }
    job = {
        "kind": "Job",
        "metadata": {
            "name": "capture",
            "namespace": "selfhosted",
            "uid": "job-uid",
            "resourceVersion": "1",
        },
        "spec": {},
    }
    node = {
        "metadata": {"name": "node"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    return journal, lease, [pod], [job], [node]


def test_only_stale_matching_actor_and_children_are_selected():
    journal, lease, pods, jobs, nodes = state()
    unrelated = deepcopy(jobs[0])
    unrelated["metadata"]["name"] = "other"
    unrelated["metadata"]["uid"] = "unrelated"
    plan = m.shared_data_watchdog_fence(
        journal, lease, pods, jobs + [unrelated], nodes, 1_000_000_000, "watchdog-uid"
    )
    assert [x["metadata"]["uid"] for x in plan["jobs"]] == ["job-uid"]
    assert [x["metadata"]["uid"] for x in plan["pods"]] == ["actor-uid"]


@pytest.mark.parametrize(
    "case",
    [
        "unexpired",
        "node-unready",
        "same-name-replaced",
        "watchdog-owner",
        "actor-is-watchdog",
    ],
)
def test_uncertain_identity_or_node_health_cannot_fence(case):
    journal, lease, pods, jobs, nodes = state()
    now = 1_000_000_000
    if case == "unexpired":
        now = 1
    if case == "node-unready":
        nodes[0]["status"]["conditions"][0]["status"] = "Unknown"
    if case == "same-name-replaced":
        pods[0]["metadata"]["uid"] = "replacement"
    if case == "watchdog-owner":
        pods.append(
            {
                "metadata": {
                    "uid": "watchdog-uid",
                    "ownerReferences": [{"kind": "Job", "uid": "job-uid"}],
                }
            }
        )
    if case == "actor-is-watchdog":
        journal["holder"]["uid"] = "watchdog-uid"
    if case == "unexpired":
        assert m.shared_data_watchdog_fence(
            journal, lease, pods, jobs, nodes, now, "watchdog-uid"
        ) == {"jobs": [], "pods": [], "expired": False}
    else:
        with pytest.raises(ValueError):
            m.shared_data_watchdog_fence(
                journal, lease, pods, jobs, nodes, now, "watchdog-uid"
            )


def test_fence_claim_is_atomic_and_preserves_prior_actor_chain():
    import jsonpatch

    journal, lease, pods, jobs, nodes = state()
    lease["metadata"]["resourceVersion"] = "7"
    actor = {
        "name": "watchdog",
        "namespace": "selfhosted",
        "uid": "watchdog-uid",
        "owners": [],
    }
    patch = m.shared_data_fence_claim(lease, journal, actor, 1_000_000_000, 300)
    claimed = jsonpatch.apply_patch(lease, patch)
    record = m.shared_data_lease_record(claimed)
    assert record["actor"] == actor
    assert record["fence_actors"] == [journal["holder"]]
    newer = deepcopy(lease)
    newer["metadata"]["resourceVersion"] = "8"
    newer["spec"]["renewTime"] = "2030-01-01T00:00:00Z"
    with pytest.raises(jsonpatch.JsonPatchTestFailed):
        jsonpatch.apply_patch(newer, patch)
    with pytest.raises(ValueError, match="expired"):
        m.shared_data_fence_claim(newer, journal, actor, 1_000_000_000, 300)
    # A crash after takeover but before journal publication cannot lose the
    # previous watchdog or the original writer identity.
    next_actor = {**actor, "name": "watchdog2", "uid": "watchdog2-uid"}
    next_lease = jsonpatch.apply_patch(
        claimed,
        m.shared_data_fence_claim(claimed, journal, next_actor, 1_000_001_000, 300),
    )
    assert {
        a["uid"] for a in m.shared_data_lease_record(next_lease)["fence_actors"]
    } == {"actor-uid", "watchdog-uid"}


def test_complete_fence_checks_child_recreation_and_node_loss():
    journal, lease, pods, jobs, nodes = state()
    plan = m.shared_data_watchdog_fence(
        journal, lease, pods, jobs, nodes, 1_000_000_000, "watchdog-uid"
    )
    assert not m.shared_data_fence_complete(plan, pods, jobs, nodes, "watchdog-uid")
    jobs[0]["spec"]["suspend"] = True
    assert m.shared_data_fence_complete(plan, [], jobs, nodes, "watchdog-uid")
    assert not m.shared_data_fence_complete(plan, pods, jobs, nodes, "watchdog-uid")
    pods[0]["status"]["phase"] = "Succeeded"
    assert m.shared_data_fence_complete(plan, pods, jobs, nodes, "watchdog-uid")
    nodes[0]["status"]["conditions"][0]["status"] = "Unknown"
    assert not m.shared_data_fence_complete(plan, pods, jobs, nodes, "watchdog-uid")


def test_operations_schedulers_and_apps_join_the_same_fence():
    registry = {
        "version": 1,
        "consumers": {"sure": {"namespace": "selfhosted", "workloads": []}},
        "maintenance": {
            "applications": ["shared-data", "restic"],
            "cronjobs": [
                {"namespace": "selfhosted", "name": "shared-data-main"},
                {"namespace": "selfhosted", "name": "shared-data-provision"},
            ],
        },
    }
    targets = m.shared_data_targets(registry, ["sure"], "backup", "backup")
    assert {"shared-data", "restic"} <= {
        r["name"] for r in targets if r["kind"] == "Application"
    }
    assert {"shared-data-main", "shared-data-provision"} <= {
        r["name"] for r in targets if r["kind"] == "CronJob"
    }


def test_current_cron_coordinator_is_exempt_but_no_other_pod_or_job_is():
    snap = {"role": "cronjob", "namespace": "selfhosted", "uid": "cron-uid"}
    job = {
        "metadata": {
            "namespace": "selfhosted",
            "uid": "job-uid",
            "ownerReferences": [{"uid": "cron-uid"}],
        }
    }
    pod = {
        "metadata": {
            "namespace": "selfhosted",
            "uid": "actor-uid",
            "ownerReferences": [{"uid": "job-uid", "kind": "Job"}],
        },
        "status": {"phase": "Running"},
    }
    assert m.shared_data_writers_stopped([snap], [pod], [job], "actor-uid")
    assert not m.shared_data_writers_stopped([snap], [pod], [job], "wrong-uid")
    other = deepcopy(pod)
    other["metadata"]["uid"] = "other-uid"
    assert not m.shared_data_writers_stopped([snap], [pod, other], [job], "actor-uid")
    other_job = deepcopy(job)
    other_job["metadata"]["uid"] = "other-job"
    assert not m.shared_data_writers_stopped(
        [snap], [pod], [job, other_job], "actor-uid"
    )


def test_manual_uploaders_are_quiescent_before_another_data_operation():
    idle = m.shared_data_operation_jobs_stopped
    current = {
        "metadata": {
            "uid": "current",
            "ownerReferences": [{"kind": "Job", "uid": "current-job"}],
        },
        "status": {"phase": "Running"},
    }
    upload = {
        "metadata": {
            "uid": "upload-job",
            "namespace": "selfhosted",
            "labels": {"home-ops/data-operation": "previous"},
        },
        "spec": {},
        "status": {},
    }
    job = {
        "metadata": {
            "uid": "current-job",
            "labels": {"home-ops/data-operation": "current"},
        },
        "spec": {},
        "status": {},
    }
    assert idle([current], [job], "current")
    assert not idle([current], [job, upload], "current")
    upload["status"] = {"conditions": [{"type": "Complete", "status": "True"}]}
    upload["status"]["active"] = 1
    assert not idle([current], [job, upload], "current")
    upload["status"]["active"] = 0
    old = {
        "metadata": {
            "uid": "old",
            "ownerReferences": [{"kind": "Job", "uid": "upload-job"}],
        },
        "status": {"phase": "Running"},
    }
    assert not idle([current, old], [job, upload], "current")
    old["status"]["phase"] = "Succeeded"
    assert idle([current, old], [job, upload], "current")
    retry = {
        "metadata": {
            "uid": "retry",
            "ownerReferences": [{"kind": "Job", "uid": "current-job"}],
        },
        "status": {"phase": "Running"},
    }
    assert not idle([current, retry], [job], "current")


def test_watchdog_stays_independent_of_normal_job_barriers():
    watchdog = {
        "metadata": {
            "uid": "watchdog-job",
            "namespace": "selfhosted",
            "labels": {"app.kubernetes.io/name": "shared-data"},
            "ownerReferences": [{"kind": "CronJob", "name": "shared-data-watchdog"}],
        },
        "spec": {},
        "status": {},
    }
    assert m.shared_data_operation_jobs_stopped([], [watchdog], "current")


def test_generation_claim_requires_same_successful_job_and_healthy_termination():
    claim = {
        "operation": "old",
        "upload_job": {"uid": "job", "name": "upload", "namespace": "selfhosted"},
    }
    job = {
        "metadata": {
            "uid": "job",
            "name": "upload",
            "namespace": "selfhosted",
            "labels": {"home-ops/data-operation": "old"},
        },
        "status": {"conditions": [{"type": "Complete", "status": "True"}]},
    }
    node = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    safe = m.shared_data_upload_claim_terminal
    assert safe(claim, [job], [], [node])
    assert not safe(claim, [], [], [node])
    changed = deepcopy(job)
    changed["metadata"]["uid"] = "other"
    assert not safe(claim, [changed], [], [node])
    pod = {
        "metadata": {"ownerReferences": [{"uid": "job", "kind": "Job"}]},
        "status": {"phase": "Running"},
    }
    assert not safe(claim, [job], [pod], [node])
    pod["status"]["phase"] = "Succeeded"
    assert safe(claim, [job], [pod], [node])
    node["status"]["conditions"][0]["status"] = "Unknown"
    assert not safe(claim, [job], [pod], [node])
