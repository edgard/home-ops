"""A disappeared child Job cannot hide its surviving unlabelled Pod."""

from tests.unit.test_data_fencing import m, state


def upload_history():
    journal, lease, _, _, nodes = state()
    journal["upload_job"] = {
        "kind": "Job",
        "uid": "upload-job",
        "name": "upload",
        "namespace": "selfhosted",
        "node_binding": "coordinator-assigned-before-start",
        "fence_nodes": [{"name": "node", "uid": "node-original"}],
    }
    pod = {
        "kind": "Pod",
        "metadata": {
            "uid": "child",
            "name": "child",
            "namespace": "selfhosted",
            "resourceVersion": "1",
            "ownerReferences": [{"kind": "Job", "uid": "upload-job"}],
        },
        "spec": {"nodeName": "node"},
        "status": {"phase": "Running"},
    }
    return journal, lease, pod, nodes


def test_absent_upload_job_still_correlates_unlabelled_live_child():
    journal, lease, pod, nodes = upload_history()
    assert not m.shared_data_recovery_fenced(journal, lease, [pod], [], nodes=nodes)
    plan = m.shared_data_watchdog_fence(
        journal, lease, [pod], [], nodes, 1_000_000_000, "watchdog"
    )
    assert plan["pods"] == [pod]
    assert not m.shared_data_fence_complete(plan, [pod], [], nodes, "watchdog")
    pod["status"]["phase"] = "Succeeded"
    assert m.shared_data_fence_complete(plan, [pod], [], nodes, "watchdog")
    assert m.shared_data_fence_complete(plan, [], [], nodes, "watchdog")


def test_bound_upload_job_name_cannot_be_replaced_after_label_loss():
    import pytest

    journal, lease, _, nodes = upload_history()
    job = {
        "kind": "Job",
        "metadata": {
            "uid": "replacement",
            "name": "upload",
            "namespace": "selfhosted",
            "resourceVersion": "1",
        },
        "spec": {"suspend": True, "template": {"spec": {"nodeName": "node"}}},
    }
    with pytest.raises(ValueError, match="child|upload|replaced"):
        m.shared_data_watchdog_fence(
            journal, lease, [], [job], nodes, 1_000_000_000, "watchdog"
        )


def test_previous_completed_operation_child_does_not_rebind_new_orphan():
    journal, lease, _, nodes = upload_history()
    journal["phase"] = "complete"
    journal["operation_id"] = "previous"
    journal["upload_job"]["fence_nodes"] = [{"name": "old-node", "uid": "old"}]
    plan = m.shared_data_watchdog_fence(
        journal, lease, [], [], nodes, 1_000_000_000, "watchdog"
    )
    assert plan["upload_job"] == {}
    assert plan["nodes"] == [{"name": "node", "uid": "node-original"}]
