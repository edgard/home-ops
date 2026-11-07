"""Exact generation Job mounts and durable upload claims through real Ansible."""

import hashlib
import json
import sys

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.support.runtime import ROOT, load_module, run_role


@pytest.mark.parametrize("binding_failure", [False, True])
def test_upload_job_is_new_digest_bound_and_claimed_before_release(
    tmp_path, binding_failure
):
    objects, variables = api.scenario_objects()
    variables["shared_data_registry"]["consumers"]["paperless"]["pvcs"] = [
        "selfhosted/paperless"
    ]
    variables["shared_data_registry"]["consumers"]["paperless"]["backend"] = "sqlite"
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
        state["fail_upload_binding"] = binding_failure
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
        if binding_failure:
            assert result.returncode != 0, result.stdout + result.stderr
            job = next(row for row in state["objects"].values() if row["kind"] == "Job")
            assert job["spec"]["suspend"] is True
            claim = json.loads(
                (
                    staging
                    / "uploads"
                    / (variables["shared_data_operation_id"] + ".json")
                ).read_text()
            )
            assert "upload_job" not in claim
            assert not any(
                event["method"] == "PATCH"
                and isinstance(event["body"], list)
                and any(
                    row.get("path") == "/spec/suspend" and row.get("value") is False
                    for row in event["body"]
                )
                for event in state["events"]
            )
            return
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
        assert job["spec"]["suspend"] is False
        assert pod["nodeName"] == "node"
        assert pod["automountServiceAccountToken"] is False
        assert claim["upload_job"]["fence_nodes"] == [
            {"name": "node", "uid": "node-uid"}
        ]
        created = next(
            i
            for i, event in enumerate(state["events"])
            if event["method"] == "POST" and event["body"].get("kind") == "Job"
        )
        assert state["events"][created]["body"]["spec"]["suspend"] is True
        started = next(
            i
            for i, event in enumerate(state["events"])
            if event["method"] == "PATCH"
            and event["path"] == api.path_for(job)
            and isinstance(event["body"], list)
            and any(
                row.get("path") == "/spec/suspend" and row.get("value") is False
                for row in event["body"]
            )
        )
        bound = next(
            i
            for i, event in enumerate(state["events"])
            if event["method"] == "PATCH"
            and isinstance(event["body"], list)
            and any(
                row.get("path") == "/data/journal.json"
                and json.loads(row["value"]).get("upload_job", {}).get("uid")
                == job["metadata"]["uid"]
                for row in event["body"]
            )
        )
        assert created < bound < started


@pytest.mark.parametrize(
    "case", ["complete", "pending-receipt", "interrupted", "legacy", "replacement"]
)
def test_exact_bound_upload_releases_only_verified_generation_for_retention(
    tmp_path, case, monkeypatch
):
    objects, variables = api.scenario_objects()
    monkeypatch.syspath_prepend(str(ROOT / "ansible/roles/shared_data/files"))
    capture = load_module("shared_data/files/capture.py")
    maintenance = load_module("shared_data/filter_plugins/maintenance.py")
    import jsonpatch

    staging = tmp_path / "staging"
    for name in ("uploads", "uploaded", "generations", "scratch"):
        (staging / name).mkdir(parents=True)
    for index in range(4):
        operation = "old" if index == 0 else "keep-" + str(index)
        generation = staging / "generations" / operation / ".home-ops"
        generation.mkdir(parents=True)
        manifest = generation / "manifest.json"
        manifest.write_text("synthetic immutable manifest " + str(index))
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (staging / "uploaded" / (operation + ".json")).write_text(
            json.dumps(
                {
                    "operation": operation,
                    "manifest_sha256": digest,
                    "snapshot": "b" * 64,
                    "status": "ok",
                }
            )
        )
    job = api.obj(
        "Job", "old-upload", "selfhosted", {"template": {"spec": {"nodeName": "node"}}}
    )
    job["metadata"]["labels"] = {"home-ops/data-operation": "old"}
    job["status"] = {"conditions": [{"type": "Complete", "status": "True"}]}
    pod = api.obj("Pod", "old-upload-pod", "selfhosted")
    pod["status"] = {"phase": "Succeeded"}
    pod["metadata"]["ownerReferences"] = [
        {"uid": job["metadata"]["uid"], "kind": "Job"}
    ]
    claim = {
        "operation": "old",
        "manifest_sha256": json.loads((staging / "uploaded/old.json").read_text())[
            "manifest_sha256"
        ],
        "upload_job": {
            "uid": job["metadata"]["uid"],
            "name": job["metadata"]["name"],
            "namespace": "selfhosted",
            "node_binding": "coordinator-assigned-before-start",
            "fence_nodes": [{"name": "node", "uid": "node-uid"}],
        },
    }
    if case == "legacy":
        claim["upload_job"].pop("fence_nodes")
    if case == "interrupted":
        pod["status"]["phase"] = "Running"
    if case == "pending-receipt":
        receipt = json.loads((staging / "uploaded/old.json").read_text())
        receipt["status"] = "pending"
        (staging / "uploaded/old.json").write_text(json.dumps(receipt))
    claim_path = staging / "uploads/old.json"
    claim_path.write_text(json.dumps(claim))
    selected_before = (staging / "generations/old/.home-ops/manifest.json").read_bytes()
    unselected = tmp_path / "unselected"
    unselected.write_text("preserve")
    actor = {
        "kind": "Pod",
        "uid": "coordinator-uid",
        "name": "coordinator",
        "namespace": "selfhosted",
        "owners": [],
        "fence_nodes": [{"name": "node", "uid": "node-uid"}],
    }
    lease = api.obj("Lease", "shared-data-operation", "selfhosted")
    lease = jsonpatch.apply_patch(
        lease,
        maintenance.shared_data_lease_takeover(
            lease, "", "test-backup", "backup", actor, 1000000000
        ),
    )
    objects += [job, pod, lease]
    registry = tmp_path / "registry.yaml"
    variables["shared_data_registry"]["consumers"]["paperless"]["pvcs"] = [
        "selfhosted/paperless"
    ]
    variables["shared_data_registry"]["consumers"]["paperless"]["backend"] = "sqlite"
    registry.write_text(yaml.safe_dump(variables["shared_data_registry"]))
    variables.update(
        shared_data_executor=actor,
        shared_data_prior_upload=claim,
        shared_data_staging=str(staging),
        shared_data_registry_file=str(registry),
        shared_data_python=sys.executable,
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        if case == "replacement":
            state["objects"]["/api/v1/nodes/node"]["metadata"]["uid"] = "replacement"
        result = run_role(
            tmp_path,
            "shared_data",
            "reconcile_upload",
            {**connection, **variables},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        if case == "complete":
            assert result.returncode == 0, result.stdout + result.stderr
            assert not claim_path.exists()
            assert api.path_for(job) not in state["objects"]
            capture.prune_generations(staging / "generations")
            assert not (staging / "generations/old").exists()
            assert len(list((staging / "generations").iterdir())) == 2
        else:
            assert claim_path.exists(), result.stdout + result.stderr
            assert api.path_for(job) in state["objects"]
            capture.prune_generations(staging / "generations")
            assert (
                staging / "generations/old/.home-ops/manifest.json"
            ).read_bytes() == selected_before
        assert unselected.read_text() == "preserve"
