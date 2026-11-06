"""Exact generation Job mounts and durable upload claims through real Ansible."""

import json

from tests.integration import test_data_maintenance as api
from tests.support.runtime import ROOT, run_role


def test_upload_job_is_new_digest_bound_and_claimed_before_release(tmp_path):
    objects, variables = api.scenario_objects()
    variables["shared_data_registry"]["consumers"]["paperless"]["pvcs"] = [
        "selfhosted/paperless"
    ]
    staging = tmp_path / "stage"
    (staging / "uploads").mkdir(parents=True)
    variables.update(
        shared_data_staging=str(staging),
        shared_data_generation={"manifest_sha256": "a" * 64},
        shared_data_image="ghcr.io/example/tools@sha256:" + "b" * 64,
        shared_data_legacy_pvcs=["selfhosted/unchanged"],
        shared_data_upload_wait=False,
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **variables},
            after=[
                {
                    "ansible.builtin.include_role": {
                        "name": "shared_data",
                        "tasks_from": "create_upload",
                        "apply": {
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
                        },
                    }
                },
            ],
            env={"ANSIBLE_ROLES_PATH": str(ROOT / "ansible/roles")},
            timeout=240,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        jobs = [o for o in state["objects"].values() if o["kind"] == "Job"]
        assert len(jobs) == 1
        job = jobs[0]
        pod = job["spec"]["template"]["spec"]
        assert "fsGroup" not in pod.get("securityContext", {})
        container = pod["containers"][0]
        assert container["image"] == variables["shared_data_image"]
        args = json.loads(container["args"][-1])
        assert args["shared_data_manifest_sha256"] == "a" * 64
        mounts = {m["mountPath"]: m for m in container["volumeMounts"]}
        generation = "generations/" + variables["shared_data_operation_id"]
        assert mounts["/generation"]["subPath"] == generation
        assert "/staging" not in mounts
        assert mounts["/staging/uploaded"]["subPath"] == "uploaded"
        assert mounts["/scratch"]["subPath"] == "scratch"
        for pvc in variables["shared_data_registry"]["consumers"]["paperless"]["pvcs"]:
            assert mounts["/data/appdata/" + pvc]["subPath"] == generation + "/" + pvc
        assert mounts["/data/appdata/.home-ops"]["subPath"] == generation + "/.home-ops"
        claim = json.loads(
            (
                staging / "uploads" / (variables["shared_data_operation_id"] + ".json")
            ).read_text()
        )
        assert claim["upload_job"]["uid"] == job["metadata"]["uid"]
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["upload_job"] == claim["upload_job"]
        assert journal["phase"] == "held"
