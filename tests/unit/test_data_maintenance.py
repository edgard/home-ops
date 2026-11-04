"""Maintenance planning catches lost fences, unsafe recovery and lossy restoration."""

from copy import deepcopy

import pytest


@pytest.fixture
def maintenance(module_loader):
    return module_loader("shared_data/filter_plugins/maintenance.py")


def resource(kind="Application", spec=None):
    return {
        "apiVersion": "argoproj.io/v1alpha1" if kind == "Application" else "apps/v1",
        "kind": kind,
        "metadata": {
            "name": "paperless",
            "namespace": "selfhosted",
            "uid": "uid-1",
            "resourceVersion": "8",
        },
        "spec": spec or {},
    }


@pytest.mark.parametrize(
    "policy",
    [None, {}, {"automated": {"selfHeal": True, "prune": True}, "retry": {"limit": 2}}],
)
def test_root_refence_preserves_original_policy_for_exact_restoration(
    maintenance, policy
):
    original = resource(spec={} if policy is None else {"syncPolicy": policy})
    snapshot = maintenance.shared_data_snapshot({"role": "root"}, original)
    current = deepcopy(original)
    patch = maintenance.shared_data_patch(snapshot, current, False)
    import jsonpatch

    held = jsonpatch.apply_patch(current, patch)
    assert "automated" not in held["spec"]["syncPolicy"]
    # A running root sync may replace the fence: reapplying never records it as original.
    held["spec"]["syncPolicy"] = {"automated": {"selfHeal": True}}
    held = jsonpatch.apply_patch(
        held, maintenance.shared_data_patch(snapshot, held, False)
    )
    restored = jsonpatch.apply_patch(
        held, maintenance.shared_data_patch(snapshot, held, True)
    )
    assert restored["spec"] == original["spec"]


@pytest.mark.parametrize(
    "kind,field,role",
    [
        ("Deployment", "replicas", "workload"),
        ("CronJob", "suspend", "cronjob"),
        ("ApplicationSet", "syncPolicy", "appset"),
    ],
)
@pytest.mark.parametrize("present", [False, True])
def test_restore_preserves_absent_versus_present_fields(
    maintenance, kind, field, role, present
):
    import jsonpatch

    value = {
        "replicas": 3,
        "suspend": False,
        "syncPolicy": {"preserveResourcesOnDeletion": True},
    }[field]
    original = resource(kind, {field: value} if present else {})
    if kind == "Deployment":
        original["spec"]["selector"] = {"matchLabels": {"app": "paperless"}}
    snapshot = maintenance.shared_data_snapshot({"role": role}, original)
    held = jsonpatch.apply_patch(
        original, maintenance.shared_data_patch(snapshot, original, False)
    )
    restored = jsonpatch.apply_patch(
        held, maintenance.shared_data_patch(snapshot, held, True)
    )
    assert restored["spec"] == original["spec"]


def test_recreated_resource_is_not_modified(maintenance):
    original = resource()
    snapshot = maintenance.shared_data_snapshot({"role": "root"}, original)
    original["metadata"]["uid"] = "replacement"
    with pytest.raises(ValueError, match="identity"):
        maintenance.shared_data_patch(snapshot, original, True)


def test_lease_claim_is_atomic_and_refuses_conflicting_owner(maintenance):
    lease = {
        "metadata": {"resourceVersion": "5"},
        "spec": {
            "holderIdentity": "other:uid",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    }
    with pytest.raises(ValueError, match="owned"):
        maintenance.shared_data_lease_claim(lease, "backup", "uid", 1000000000, 60)
    lease["spec"] = {}
    patch = maintenance.shared_data_lease_claim(lease, "backup", "uid", 1000000000, 60)
    assert patch[0] == {"op": "test", "path": "/metadata/resourceVersion", "value": "5"}
    assert patch[1] == {"op": "test", "path": "/spec", "value": {}}
    assert patch[-1]["value"]["holderIdentity"] == "backup:uid"


@pytest.mark.parametrize("kind", ["restore", "migration", "rotation", "provision"])
def test_destructive_recovery_is_held_for_operator(maintenance, kind):
    journal = {
        "operation_id": "op",
        "operation_kind": kind,
        "holder": {"uid": "old", "namespace": "selfhosted", "name": "coordinator"},
    }
    lease = {
        "spec": {
            "holderIdentity": "op:old",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        }
    }
    assert not maintenance.shared_data_recovery(journal, lease, [], [], 1000000000)[
        "resume"
    ]


def test_expired_backup_requires_old_coordinator_and_children_fenced(maintenance):
    journal = {
        "operation_id": "op",
        "operation_kind": "backup",
        "holder": {"uid": "old", "namespace": "selfhosted", "name": "coordinator"},
    }
    lease = {
        "spec": {
            "holderIdentity": "op:old",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        }
    }
    pod = {
        "metadata": {"uid": "old", "name": "coordinator", "namespace": "selfhosted"},
        "status": {"phase": "Running"},
    }
    assert not maintenance.shared_data_recovery(journal, lease, [pod], [], 1000000000)[
        "resume"
    ]
    pod["metadata"]["deletionTimestamp"] = "2000-01-01T00:00:00Z"
    assert not maintenance.shared_data_recovery(journal, lease, [pod], [], 1000000000)[
        "resume"
    ]
    child = {
        "metadata": {"labels": {"home-ops/data-operation": "op"}},
        "spec": {},
        "status": {"active": 1},
    }
    assert not maintenance.shared_data_recovery(
        journal, lease, [], [child], 1000000000
    )["resume"]
    child["spec"]["suspend"] = True
    child["status"]["active"] = 0
    assert maintenance.shared_data_recovery(journal, lease, [], [child], 1000000000)[
        "resume"
    ]
    lease["spec"]["renewTime"] = "2100-01-01T00:00:00Z"
    assert not maintenance.shared_data_recovery(journal, lease, [], [], 1000000000)[
        "resume"
    ]


def test_cronjob_owned_jobs_and_selected_workload_pods_must_finish(maintenance):
    snapshots = [
        {"role": "cronjob", "uid": "cron", "namespace": "selfhosted"},
        {
            "role": "workload",
            "namespace": "selfhosted",
            "selector": {"matchLabels": {"app": "paperless"}},
        },
    ]
    job = {
        "metadata": {"namespace": "selfhosted", "ownerReferences": [{"uid": "cron"}]},
        "status": {"active": 1},
    }
    pod = {
        "metadata": {"namespace": "selfhosted", "labels": {"app": "paperless"}},
        "status": {"phase": "Running"},
    }
    assert not maintenance.shared_data_writers_stopped(snapshots, [], [job])
    job["status"] = {"conditions": [{"type": "Complete", "status": "True"}]}
    assert maintenance.shared_data_writers_stopped(snapshots, [], [job])
    assert not maintenance.shared_data_writers_stopped(snapshots, [pod], [job])
    pod["metadata"]["deletionTimestamp"] = "now"
    assert not maintenance.shared_data_writers_stopped(snapshots, [pod], [job])
    pod["status"]["phase"] = "Succeeded"
    assert maintenance.shared_data_writers_stopped(snapshots, [pod], [job])


def test_targets_are_explicit_and_include_tuppr_fence(maintenance):
    registry = {
        "version": 1,
        "consumers": {
            "paperless": {
                "enabled": False,
                "namespace": "selfhosted",
                "workloads": [{"kind": "Deployment", "name": "paperless"}],
                "cronjobs": [{"name": "paperless-export"}],
            }
        },
    }
    targets = maintenance.shared_data_targets(
        registry, ["paperless"], "operation", "backup"
    )
    assert [row["name"] for row in targets if row["role"] == "application"] == [
        "paperless",
        "tuppr",
    ]
    assert any(
        row["kind"] == "CronJob" and row["name"] == "paperless-export"
        for row in targets
    )
    for bad in ["", "../bad", "UPPER", "space name"]:
        with pytest.raises(ValueError):
            maintenance.shared_data_targets(registry, ["paperless"], bad, "backup")
    with pytest.raises(ValueError):
        maintenance.shared_data_targets(registry, ["unknown"], "op", "backup")


def test_upgrade_unknown_or_active_phase_blocks_maintenance(maintenance):
    assert maintenance.shared_data_upgrades_idle([{"status": {"phase": "Completed"}}])
    assert not maintenance.shared_data_upgrades_idle(
        [{"status": {"phase": "InProgress"}}]
    )
    assert not maintenance.shared_data_upgrades_idle([{}])


def test_terminated_coordinator_job_must_not_be_able_to_restart(maintenance):
    journal = {
        "operation_id": "op",
        "holder": {
            "uid": "old",
            "name": "coordinator",
            "namespace": "selfhosted",
            "owners": [{"kind": "Job", "uid": "job-uid"}],
        },
    }
    job = {"metadata": {"uid": "job-uid"}, "spec": {}, "status": {"active": 0}}
    assert not maintenance.shared_data_coordinator_fenced(journal, [], [job])
    job["spec"]["suspend"] = True
    assert maintenance.shared_data_coordinator_fenced(journal, [], [job])


def test_unlabelled_child_pod_of_selected_job_blocks_recovery(maintenance):
    journal = {
        "operation_id": "op",
        "holder": {
            "uid": "old",
            "name": "coordinator",
            "namespace": "selfhosted",
            "owners": [{"kind": "Job", "uid": "job-uid"}],
        },
    }
    job = {
        "metadata": {"uid": "job-uid"},
        "spec": {"suspend": True},
        "status": {"active": 0},
    }
    pod = {
        "metadata": {
            "name": "replacement",
            "namespace": "selfhosted",
            "ownerReferences": [{"uid": "job-uid"}],
        },
        "status": {"phase": "Running"},
    }
    assert not maintenance.shared_data_coordinator_fenced(journal, [pod], [job])


def test_recovery_does_not_renew_unexpired_lease_or_live_owner(maintenance):
    journal = {
        "operation_id": "op",
        "operation_kind": "backup",
        "holder": {"uid": "old", "name": "coordinator", "namespace": "selfhosted"},
    }
    lease = {
        "spec": {
            "holderIdentity": "op:old",
            "renewTime": "2100-01-01T00:00:00Z",
            "leaseDurationSeconds": 900,
        }
    }
    assert not maintenance.shared_data_recovery(journal, lease, [], [], 1000000000).get(
        "record", False
    )


def test_expired_fenced_destructive_recovery_records_operator_hold(maintenance):
    journal = {
        "operation_id": "op",
        "operation_kind": "restore",
        "holder": {"uid": "old", "name": "coordinator", "namespace": "selfhosted"},
    }
    lease = {
        "spec": {
            "holderIdentity": "op:old",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        }
    }
    result = maintenance.shared_data_recovery(journal, lease, [], [], 1000000000)
    assert result["record"] and not result["resume"]


def test_initial_lease_without_serialized_spec_can_be_claimed_atomically(maintenance):
    import jsonpatch

    lease = {"metadata": {"resourceVersion": "9"}}
    patch = maintenance.shared_data_lease_claim(lease, "op", "uid", 1000000000, 60)
    claimed = jsonpatch.apply_patch(lease, patch)
    assert claimed["spec"]["holderIdentity"] == "op:uid"
    assert patch[0] == {"op": "test", "path": "/metadata/resourceVersion", "value": "9"}


def upgrade_worker(kind="Job", *, owner_uid="upgrade-old", phase="Pending"):
    metadata = {
        "name": "upgrade-node",
        "namespace": "platform-system",
        "uid": "job-old" if kind == "Job" else "pod-old",
        "labels": {
            "app.kubernetes.io/name": "kubernetes-upgrade",
            "app.kubernetes.io/part-of": "tuppr",
            "app.kubernetes.io/instance": "kubernetes",
            "tuppr.home-operations.com/target-node": "node",
        },
        "ownerReferences": [
            {
                "apiVersion": "tuppr.home-operations.com/v1alpha1"
                if kind == "Job"
                else "batch/v1",
                "kind": "KubernetesUpgrade" if kind == "Job" else "Job",
                "name": "kubernetes" if kind == "Job" else "upgrade-node",
                "uid": owner_uid,
                "controller": True,
            }
        ],
    }
    return {
        "apiVersion": "batch/v1" if kind == "Job" else "v1",
        "kind": kind,
        "metadata": metadata,
        "spec": {"backoffLimit": 3},
        "status": {"active": 0} if kind == "Job" else {"phase": phase},
    }


@pytest.mark.parametrize("cr_phase", ["Pending", "Completed", None])
def test_upgrade_job_blocks_even_without_active_cr_phase(maintenance, cr_phase):
    plans = (
        []
        if cr_phase is None
        else [
            {
                "metadata": {"uid": "upgrade-new", "name": "kubernetes"},
                "status": {"phase": cr_phase},
            }
        ]
    )
    job = upgrade_worker()
    assert not maintenance.shared_data_upgrade_workers_idle(plans, [job], [])
    job["spec"]["suspend"] = True
    assert not maintenance.shared_data_upgrade_workers_idle(plans, [job], [])


def test_upgrade_owner_uid_correlation_does_not_depend_on_names_or_labels(maintenance):
    job = upgrade_worker()
    job["metadata"]["labels"] = {}
    # A stale CR owner with no current row is still correlated by API group/kind and UID.
    assert not maintenance.shared_data_upgrade_workers_idle([], [job], [])
    job["metadata"]["ownerReferences"] = [
        {"uid": "current-upgrade-uid", "kind": "Other"}
    ]
    assert not maintenance.shared_data_upgrade_workers_idle(
        [{"metadata": {"uid": "current-upgrade-uid"}}], [job], []
    )
    job["metadata"]["ownerReferences"] = [
        {"uid": "different-uid", "kind": "Other", "name": "kubernetes"}
    ]
    assert maintenance.shared_data_upgrade_workers_idle(
        [{"metadata": {"uid": "current-upgrade-uid", "name": "kubernetes"}}], [job], []
    )


def test_terminal_upgrade_job_still_requires_its_pods_terminal(maintenance):
    job = upgrade_worker()
    job["status"] = {
        "active": 0,
        "conditions": [{"type": "Complete", "status": "True"}],
    }
    pod = upgrade_worker("Pod", owner_uid="job-old", phase="Running")
    pod["metadata"]["labels"] = {}
    assert not maintenance.shared_data_upgrade_workers_idle([], [job], [pod])
    pod["metadata"]["deletionTimestamp"] = "2026-11-04T00:00:00Z"
    assert not maintenance.shared_data_upgrade_workers_idle([], [job], [pod])
    pod["status"]["phase"] = "Succeeded"
    assert maintenance.shared_data_upgrade_workers_idle([], [job], [pod])
    job["status"]["active"] = 1
    assert not maintenance.shared_data_upgrade_workers_idle([], [job], [])


def test_upgrade_pod_surviving_deleted_job_is_correlated_by_upstream_labels(
    maintenance,
):
    pod = upgrade_worker("Pod", owner_uid="deleted-job", phase="Running")
    assert not maintenance.shared_data_upgrade_workers_idle([], [], [pod])
    pod["metadata"]["labels"]["app.kubernetes.io/name"] = "talos-upgrade-hook"
    assert not maintenance.shared_data_upgrade_workers_idle([], [], [pod])
    pod["status"]["phase"] = "Failed"
    assert maintenance.shared_data_upgrade_workers_idle([], [], [pod])


def test_pod_owner_name_reuse_does_not_replace_job_uid_correlation(maintenance):
    job = upgrade_worker()
    job["status"] = {"conditions": [{"type": "Complete", "status": "True"}]}
    pod = upgrade_worker("Pod", owner_uid="unrelated-job-uid", phase="Running")
    pod["metadata"]["labels"] = {}
    assert maintenance.shared_data_upgrade_workers_idle([], [job], [pod])


def test_owner_only_renewal_cannot_reclaim_released_lease(maintenance):
    lease = {"metadata": {"resourceVersion": "10"}, "spec": {"holderIdentity": ""}}
    with pytest.raises(ValueError, match="owned"):
        maintenance.shared_data_lease_claim(lease, "op", "old", 1000000000, 60, False)


def actor(uid="recoverer"):
    return {"uid": uid, "name": uid, "namespace": "selfhosted", "owners": []}


def test_recovery_takeover_is_distinct_uid_and_only_one_cas_wins(maintenance):
    import jsonpatch

    lease = {
        "metadata": {"resourceVersion": "10"},
        "spec": {
            "holderIdentity": "op:old",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    }
    patch = maintenance.shared_data_lease_takeover(
        lease, "op:old", "op", "backup", actor("new-1"), 1000000000, 60, "journaled"
    )
    claimed = jsonpatch.apply_patch(lease, patch)
    assert claimed["spec"]["holderIdentity"] == "op:new-1"
    payload = maintenance.shared_data_lease_record(claimed)
    assert payload["actor"]["uid"] == "new-1" and payload["stage"] == "journaled"
    with pytest.raises(ValueError, match="changed"):
        maintenance.shared_data_lease_takeover(
            claimed,
            "op:old",
            "op",
            "backup",
            actor("new-2"),
            1000000000,
            60,
            "journaled",
        )
    with pytest.raises(ValueError, match="owned"):
        maintenance.shared_data_lease_claim(claimed, "op", "old", 1000000000, 60, False)


def test_orphan_claim_records_identity_before_journal_and_requires_fenced_expiry(
    maintenance,
):
    import jsonpatch

    lease = {"metadata": {"resourceVersion": "1"}, "spec": {}}
    lease = jsonpatch.apply_patch(
        lease,
        maintenance.shared_data_lease_takeover(
            lease, "", "op", "backup", actor("old"), 1000000000, 60, "claimed"
        ),
    )
    assert not maintenance.shared_data_orphan_releasable(lease, [], [], 1000000001)
    assert maintenance.shared_data_orphan_releasable(lease, [], [], 1000000100)
    pod = {
        "metadata": {"uid": "old", "name": "old", "namespace": "selfhosted"},
        "status": {"phase": "Running"},
    }
    assert not maintenance.shared_data_orphan_releasable(lease, [pod], [], 1000000100)
    payload = maintenance.shared_data_lease_record(lease)
    payload["stage"] = "journaled"
    import json

    lease["metadata"]["annotations"]["home-ops/data-coordinator"] = json.dumps(payload)
    assert not maintenance.shared_data_orphan_releasable(lease, [], [], 1000000100)


def test_recovery_checks_last_takeover_actor_as_well_as_original_holder(maintenance):
    journal = {
        "operation_id": "op",
        "holder": actor("original"),
        "coordinator": actor("previous-watchdog"),
    }
    live = {
        "metadata": {
            "uid": "previous-watchdog",
            "name": "previous-watchdog",
            "namespace": "selfhosted",
        },
        "status": {"phase": "Running"},
    }
    assert not maintenance.shared_data_coordinator_fenced(journal, [live], [])


def test_completed_cleanup_requires_exact_original_identity_and_field_presence(
    maintenance,
):
    snapshot = {
        "uid": "root-old",
        "field": "syncPolicy",
        "present": False,
        "value": None,
    }
    original = {"metadata": {"uid": "root-old"}, "spec": {}}
    assert maintenance.shared_data_snapshot_restored(snapshot, original)
    original["spec"]["syncPolicy"] = {}
    assert not maintenance.shared_data_snapshot_restored(snapshot, original)
    snapshot.update(present=True, value={"automated": {"selfHeal": True}})
    assert not maintenance.shared_data_snapshot_restored(snapshot, original)
    original["spec"]["syncPolicy"] = {"automated": {"selfHeal": True}}
    assert maintenance.shared_data_snapshot_restored(snapshot, original)
    original["metadata"]["uid"] = "root-recreated"
    assert not maintenance.shared_data_snapshot_restored(snapshot, original)
