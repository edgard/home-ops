"""Local Tasks submit reviewed, bounded Jobs with the same in-cluster role."""

import json

import pytest

from tests.integration import test_data_maintenance as api
from tests.support.data_generation import operations_image
from tests.support.runtime import run_role


@pytest.mark.parametrize(
    "action", ["backup", "provision", "restore", "watchdog", "cleanup"]
)
def test_submission_scopes_storage_privilege_and_binds_exact_job(tmp_path, action):
    objects, variables = api.scenario_objects()
    variables.update(
        shared_data_action="submit",
        shared_data_job_action=action,
        shared_data_image=operations_image(native=False),
        shared_data_job_timeout=60,
    )

    def created(job, state):
        job["status"] = {
            "succeeded": 1,
            "conditions": [{"type": "Complete", "status": "True"}],
        }

    with api.maintenance_api(tmp_path, objects) as (connection, state):
        state["job_created"] = created
        result = run_role(tmp_path, "shared_data", "main", {**connection, **variables})
        assert result.returncode == 0, result.stdout + result.stderr
        [job] = [
            resource
            for resource in state["objects"].values()
            if resource["kind"] == "Job"
        ]
        assert isinstance(job["spec"]["activeDeadlineSeconds"], int)
        assert job["spec"]["backoffLimit"] == 0
        pod = job["spec"]["template"]["spec"]
        args = json.loads(pod["containers"][0]["args"][-1])
        assert args["shared_data_action"] == action
        assert args["shared_data_require_current_registry"] == (action != "watchdog")
        assert args["shared_data_operation_kind"] == (
            "backup" if action in {"watchdog", "cleanup"} else action
        )
        mounts = {
            mount["mountPath"]: mount for mount in pod["containers"][0]["volumeMounts"]
        }
        if action in {"watchdog", "provision", "cleanup"}:
            assert not any(
                "persistentVolumeClaim" in volume for volume in pod["volumes"]
            )
        else:
            assert "fsGroup" not in pod["securityContext"]
            assert mounts["/data/appdata"].get("readOnly", False) == (
                action == "backup"
            )
        if action == "cleanup":
            assert "/run/credentials" not in mounts
            assert "RESTIC_PASSWORD" in {
                entry["name"] for entry in pod["containers"][0]["env"]
            }
        assert "POD_UID" in {entry["name"] for entry in pod["containers"][0]["env"]}
        assert not any(
            event["path"].endswith("/applications/root") and event["method"] == "PATCH"
            for event in state["events"]
        )
