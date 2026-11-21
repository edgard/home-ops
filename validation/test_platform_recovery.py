"""File-only recovery cannot attest a usable database whose PGDATA was excluded."""

import pytest
from ansible.errors import AnsibleFilterError


def test_native_database_recovery_required_before_handoff(module_loader):
    storage = module_loader("platform/filter_plugins/storage.py")
    record = {
        "namespace": "selfhosted",
        "name": "sparkyfitness-data",
        "uid": "f75ad2e5-0023-4a7e-8132-49fe8c8e68cf",
        "dataset_guid": "121",
        "snapshot": "verified",
        "snapshot_guid": "122",
        "verification": "restic-verify",
    }
    proof = {"pool_guid": "120", "claims": [record]}
    with pytest.raises(AnsibleFilterError, match="verified recovery method"):
        storage.recovery_claims(proof, "120", [])
    record["verification"] = "native-postgresql"
    assert storage.recovery_claims(proof, "120", []) == [record]
