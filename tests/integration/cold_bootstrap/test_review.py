"""Cold review regressions execute the real source-owned API guard entry points."""

import json
from copy import deepcopy

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.integration.cold_bootstrap.test_role import (
    REVISION,
    TOKEN,
    extend_api,
    variables,
)
from tests.support.runtime import run_role


@pytest.mark.parametrize("kind", ["PersistentVolumeClaim", "Deployment"])
def test_deleted_bound_resource_refuses_before_any_mutation(
    tmp_path, monkeypatch, kind
):
    extend_api(monkeypatch)
    with api.maintenance_api(tmp_path, []) as (connection, state):
        params = variables(connection)
        target = {
            "api_version": "v1" if kind == "PersistentVolumeClaim" else "apps/v1",
            "kind": kind,
            "namespace": "selfhosted",
            "name": "paperless"
            if kind == "PersistentVolumeClaim"
            else "paperless-main",
            "uid": "bound-original",
        }
        journal = {
            "version": 1,
            "apps": ["paperless"],
            "revision": REVISION,
            "operation": "recovery-test",
            "source_sha256": params["platform_recovery_source_sha256"],
            "phase": "held",
            "token": TOKEN,
            "inventory": [target],
        }
        cm = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "shared-data-cold-recovery",
                "namespace": "selfhosted",
                "uid": "cold",
                "resourceVersion": "1",
            },
            "data": {"journal.json": json.dumps(journal)},
        }
        state["objects"][api.path_for(cm)] = deepcopy(cm)
        marker = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "must-not-create"},
        }
        result = run_role(
            tmp_path,
            "platform",
            "recovery_dispatch",
            params,
            after=[
                {
                    "kubernetes.core.k8s": {
                        "kubeconfig": connection["kubeconfig_path"],
                        "context": connection["kube_context"],
                        "state": "present",
                        "definition": marker,
                    }
                }
            ],
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert "bound recovery resource is missing" in result.stdout
        assert all(event["method"] == "GET" for event in state["events"])
        assert state["objects"][api.path_for(cm)] == cm


@pytest.mark.parametrize("change", ["database", "files"])
def test_changed_current_registry_refuses_before_provisioning(tmp_path, change):
    from tests.support.runtime import load_module

    cold = load_module("platform/filter_plugins/cold_recovery.py")
    registry = {
        "version": 1,
        "consumers": {
            "demo": {
                "namespace": "selfhosted",
                "workloads": [],
                "backend": "postgresql",
                "databases": [{"name": "demo", "owner": "demo"}],
                "pvcs": ["selfhosted/demo"],
            }
        },
        "file_consumers": {},
    }
    journal = {
        "phase": "held",
        "apps": ["demo"],
        "revision": REVISION,
        "token": TOKEN,
        "source_sha256": cold.digest({"registry": registry, "revision": REVISION}),
        "inventory": [],
    }
    changed = deepcopy(registry)
    if change == "database":
        changed["consumers"]["demo"]["databases"][0]["owner"] = "other"
    else:
        changed["consumers"]["demo"]["pvcs"] = ["selfhosted/other"]
    cm = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "shared-data-cold-recovery",
            "namespace": "selfhosted",
            "uid": "cold",
            "resourceVersion": "1",
        },
        "data": {"journal.json": json.dumps(journal)},
    }
    current = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "shared-data-registry",
            "namespace": "selfhosted",
            "uid": "current",
            "resourceVersion": "1",
        },
        "data": {"registry.yaml": yaml.safe_dump(changed)},
    }
    with api.maintenance_api(tmp_path, [cm, current]) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "current_registry",
            {
                **connection,
                "shared_data_registry": changed,
                "shared_data_journal": {"apps": ["demo"], "snapshots": []},
            },
            env={"KUBECONFIG": connection["kubeconfig_path"]},
            after=[
                {
                    "ansible.builtin.include_role": {
                        "name": "shared_data",
                        "tasks_from": "cold_restore_bind",
                    }
                },
                {
                    "ansible.builtin.command": {
                        "argv": ["touch", str(tmp_path / "destructive")]
                    }
                },
            ],
        )
        assert result.returncode != 0
        assert "restore registry source differs from bootstrap" in result.stdout
        assert not (tmp_path / "destructive").exists()
        assert all(e["method"] == "GET" for e in state["events"])


def test_admission_registry_removal_does_not_authorize_global_capability(tmp_path):
    from tests.unit.test_cold_bootstrap import registry
    from tests.unit.test_cold_review import bound_journal, receipt

    full = registry()
    full["consumers"]["other"] = {"namespace": "selfhosted", "workloads": []}
    cold = bound_journal(full)
    cold["executor"] = {"code_sha256": "d" * 64}
    proof = receipt(cold)
    resources = []
    for name, value in [
        ("shared-data-cold-recovery", cold),
        ("shared-data-operation", proof),
    ]:
        resources.append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": name,
                    "namespace": "selfhosted",
                    "uid": name,
                    "resourceVersion": "1",
                },
                "data": {"journal.json": json.dumps(value)},
            }
        )
    with api.maintenance_api(tmp_path, resources) as (connection, state):
        result = run_role(
            tmp_path,
            "platform",
            "recovery_admission",
            {**connection, "platform_recovery_registry": registry()},
        )
        assert result.returncode != 0
        assert "admission registry or receipt source differs" in result.stdout
        assert all(e["method"] == "GET" for e in state["events"])
