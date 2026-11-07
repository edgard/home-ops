"""Non-Pod native ownership is never recoverable from Pod fencing or TTL."""

from copy import deepcopy

import jsonpatch
import pytest

from tests.support.runtime import load_module

native = load_module("node_operation/filter_plugins/node_operation.py")
maintenance = load_module("shared_data/filter_plugins/maintenance.py")
cold = load_module("platform/filter_plugins/cold_executor.py")


def claim():
    lease = {
        "metadata": {
            "name": "shared-data-operation",
            "namespace": "selfhosted",
            "uid": "lease-uid",
            "resourceVersion": "1",
        },
        "spec": {},
    }
    actor = {
        "kind": "NativeCLI",
        "uid": "native-nonce",
        "name": "talos-upgrade",
        "namespace": "selfhosted",
        "original_node": {"name": "node", "uid": "node-uid"},
    }
    result = jsonpatch.apply_patch(
        lease,
        native.node_operation_claim(
            lease, "native-operation", actor, "talos-upgrade", 0, 43200
        ),
    )
    return result, actor


@pytest.mark.parametrize("phase", ["missing", "complete", "native-intent"])
def test_expired_native_claim_never_becomes_pod_recovery(phase):
    lease, actor = claim()
    journal = (
        {}
        if phase == "missing"
        else {
            "phase": phase,
            "operation_id": "native-operation",
            "operation_kind": "node-operation",
            "holder": actor,
            "coordinator": actor,
            "apps": [],
            "snapshots": [],
        }
    )
    assert not maintenance.shared_data_orphan_releasable(
        lease, [], [], 999999, "new-pod", []
    )
    if journal:
        assert not maintenance.shared_data_recovery(
            journal, lease, [], [], 999999, "new-pod", []
        )["resume"]
    with pytest.raises(ValueError):
        maintenance.shared_data_watchdog_fence(
            journal, lease, [], [], [], 999999, "new-pod"
        )
    with pytest.raises(ValueError):
        cold.cold_dispatch_ownership(lease, {}, {}, "new-cold")


def test_finalizer_without_holder_still_requires_manual_resolution():
    lease, actor = claim()
    lease["spec"]["holderIdentity"] = ""
    with pytest.raises(ValueError):
        native.node_operation_available(lease, {"phase": "complete"}, {})
    with pytest.raises(ValueError):
        cold.cold_dispatch_ownership(lease, {}, {}, "new-cold")
    with pytest.raises(ValueError):
        maintenance.shared_data_lease_takeover(
            lease, "", "next-backup", "backup", actor, 1
        )


def test_atomic_claim_refuses_changed_uid_version_or_owner():
    original = {"metadata": {"uid": "lease", "resourceVersion": "1"}, "spec": {}}
    actor = claim()[1]
    patch = native.node_operation_claim(
        original, "native-operation", actor, "talos-upgrade", 0, 43200
    )
    for mutation in ["uid", "resourceVersion", "owner"]:
        current = deepcopy(original)
        if mutation == "owner":
            current["spec"]["holderIdentity"] = "other:owner"
        else:
            current["metadata"][mutation] = "changed"
        with pytest.raises(jsonpatch.JsonPatchTestFailed):
            jsonpatch.apply_patch(current, patch)
