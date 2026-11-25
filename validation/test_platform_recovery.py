"""Prevent data loss or incomplete application recovery at first handoff."""

import pytest
from ansible.errors import AnsibleFilterError


def test_manual_recovery_requires_retained_checksum(module_loader):
    storage = module_loader("platform/filter_plugins/storage.py")
    record = {
        "namespace": "selfhosted",
        "name": "paperless",
        "uid": "f75ad2e5-0023-4a7e-8132-49fe8c8e68cf",
        "dataset_guid": "121",
        "snapshot": "verified",
        "snapshot_guid": "122",
        "verification": "retained-checksum",
    }
    proof = {"pool_guid": "120", "claims": [record]}
    assert storage.recovery_claims(proof, "120", []) == [record]
    for method in ("restic-verify", "native-postgresql"):
        record["verification"] = method
        with pytest.raises(AnsibleFilterError, match="Manual evidence requires"):
            storage.recovery_claims(proof, "120", [])


def test_direct_pool_writer_must_stop_before_restore(module_loader):
    storage = module_loader("platform/filter_plugins/storage.py")
    mount = {"name": "shared", "mountPath": "/files"}
    pod = {
        "kind": "Pod",
        "metadata": {"name": "writer", "namespace": "another-namespace"},
        "spec": {
            "containers": [{"volumeMounts": [mount]}],
            "volumes": [
                {"name": "shared", "hostPath": {"path": "/var/mnt/dpool/dump"}}
            ],
        },
    }
    inventory = [{"api_found": True, "item": {"kind": "Pod"}, "resources": [pod]}]
    assert storage.recovery_consumers(inventory, []) == ["Pod another-namespace/writer"]
    mount["readOnly"] = True
    assert storage.recovery_consumers(inventory, []) == []
