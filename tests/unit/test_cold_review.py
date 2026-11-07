"""Review regressions: immutable bindings and exact source registry are required."""

from copy import deepcopy

import pytest

from tests.support.runtime import load_module
from tests.unit.test_cold_bootstrap import cold, deployment, registry


def bound_journal(reg=None):
    reg = reg or registry()
    return {
        "version": 1,
        "phase": "held",
        "apps": ["demo"],
        "token": "t" * 32,
        "revision": "a" * 40,
        "source_sha256": cold().digest({"registry": reg, "revision": "a" * 40}),
        "inventory": [],
        "executor": {"code_sha256": "d" * 64},
    }


def receipt(journal):
    return {
        "operation_id": "restore",
        "cold_token": journal["token"],
        "apps": journal["apps"],
        "revision": journal["revision"],
        "source_sha256": journal["source_sha256"],
        "phase": "complete",
        "operation_kind": "restore",
        "recovery": {"selection_sha256": "b" * 64, "manifest_sha256": "c" * 64},
        "restore_tooling": {
            "image": "example/tools@sha256:" + "f" * 64,
            "image_revision": "f" * 40,
            "code_sha256": "d" * 64,
            "pod_uid": "pod",
        },
        "cold_steps": [
            "provision",
            "redis-provision",
            "validate",
            "postgres",
            "files",
            "redis:not-required",
            "validate",
        ],
    }


@pytest.mark.parametrize("kind", ["PersistentVolumeClaim", "Deployment"])
def test_missing_bound_inventory_is_not_a_new_allocation(kind):
    row = {
        "api_version": "v1" if kind == "PersistentVolumeClaim" else "apps/v1",
        "kind": kind,
        "namespace": "selfhosted",
        "name": "demo",
        "uid": "original",
    }
    with pytest.raises(ValueError, match="missing|identity"):
        cold().cold_bound_inventory(
            {"inventory": [row]}, [{"item": row, "resources": []}]
        )


def test_unbound_inventory_can_retry_first_creation():
    row = {
        "api_version": "v1",
        "kind": "PersistentVolumeClaim",
        "namespace": "selfhosted",
        "name": "demo",
        "uid": "",
    }
    assert cold().cold_bound_inventory({"inventory": [row]}, [])


def test_bound_identity_cannot_be_rewritten_in_inventory():
    resource = deployment()
    resource["metadata"].update(namespace="selfhosted", uid="new")
    original = {**cold().identity(resource), "uid": "original"}
    with pytest.raises(ValueError, match="identity"):
        cold().cold_record([original], resource)


@pytest.mark.parametrize("change", ["database", "files"])
def test_restore_registry_is_bound_to_bootstrap_source(change):
    reg = registry()
    reg["consumers"]["demo"].update(
        backend="postgresql",
        databases=[{"name": "demo", "owner": "demo"}],
        pvcs=["selfhosted/demo"],
    )
    journal = bound_journal(reg)
    changed = deepcopy(reg)
    if change == "database":
        changed["consumers"]["demo"]["databases"][0]["owner"] = "different"
    else:
        changed["consumers"]["demo"]["pvcs"] = ["selfhosted/elsewhere"]
    restore = {"apps": ["demo"], "snapshots": []}
    with pytest.raises(ValueError, match="registry|source"):
        load_module(
            "shared_data/filter_plugins/cold_restore.py"
        ).shared_data_cold_restore(journal, restore, changed)


def test_removed_unselected_consumer_cannot_turn_partial_into_global():
    full = registry()
    full["consumers"]["other"] = {"namespace": "selfhosted", "workloads": []}
    journal = bound_journal(full)
    with pytest.raises(ValueError, match="registry|source"):
        cold().cold_admission(journal, receipt(journal), registry())


def test_admission_requires_matching_receipt_digest_and_actual_registry():
    reg = registry()
    journal = bound_journal(reg)
    proof = receipt(journal)
    assert (
        cold().cold_admission(journal, proof, reg)["source_sha256"]
        == journal["source_sha256"]
    )
    proof["source_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="registry|source"):
        cold().cold_admission(journal, proof, reg)
