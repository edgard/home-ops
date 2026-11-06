"""Isolated source resources through the actual held recovery role."""

import json

from tests.integration import test_data_maintenance as api
from tests.support.runtime import ROOT, run_role


def test_source_uses_verified_rdb_emptydir_hashed_acl_and_exact_journal_actors(
    tmp_path,
):
    objects, variables = api.scenario_objects()
    recovery = tmp_path / "staging/restores/test-backup/data/appdata"
    (recovery / ".home-ops").mkdir(parents=True)
    (recovery / ".home-ops/manifest.json").write_text(
        json.dumps({"files": {".home-ops/redis.rdb": "a" * 64}})
    )
    variables.update(
        shared_data_staging=str(tmp_path / "staging"),
        shared_data_recovery={"root": str(recovery)},
        shared_data_image="ghcr.io/example/ops@sha256:" + "b" * 64,
    )

    def created(resource, state):
        if resource["kind"] == "Pod":
            resource["status"] = {
                "phase": "Running",
                "conditions": [{"type": "Ready", "status": "True"}],
            }

    with api.maintenance_api(tmp_path, objects) as (connection, state):
        state["created"] = created
        apply = {
            "module_defaults": {
                module: {
                    "kubeconfig": connection["kubeconfig_path"],
                    "context": connection["kube_context"],
                }
                for module in [
                    "kubernetes.core.k8s",
                    "kubernetes.core.k8s_info",
                    "kubernetes.core.k8s_json_patch",
                ]
            }
        }
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **variables},
            after=[
                {
                    "ansible.builtin.include_role": {
                        "name": "shared_data",
                        "tasks_from": "create_redis_source",
                        "apply": apply,
                    }
                }
            ],
            env={"ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        pod = state["objects"][
            "/api/v1/namespaces/selfhosted/pods/shared-data-redis-recovery"
        ]
        spec = pod["spec"]
        assert "fsGroup" not in spec["securityContext"]
        assert spec["automountServiceAccountToken"] is False
        assert spec["securityContext"]["runAsUser"] == 999
        assert (
            spec["initContainers"][0]["command"][
                spec["initContainers"][0]["command"].index("--sha256") + 1
            ]
            == "a" * 64
        )
        assert all(
            mount["name"] != "staging"
            for mount in spec["containers"][0]["volumeMounts"]
        )
        assert any(
            volume["name"] == "data" and "emptyDir" in volume
            for volume in spec["volumes"]
        )
        assert "--appendonly" in spec["containers"][0]["args"]
        secret = state["objects"][
            "/api/v1/namespaces/selfhosted/secrets/shared-data-redis-recovery"
        ]
        assert set(secret["data"]) == {"redis_recovery_password"}
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert {entry["uid"] for entry in journal["redis_source"]} == {
            "created-shared-data-redis-recovery"
        }
        assert {entry["kind"] for entry in journal["redis_source"]} == {
            "Pod",
            "Service",
            "Secret",
        }
        assert journal["phase"] == "held"
