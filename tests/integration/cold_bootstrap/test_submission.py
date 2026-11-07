"""Cold jobs require an image containing cold role logic before running Ansible."""

import json
import subprocess

from tests.integration import test_data_maintenance as api
from tests.support.data_generation import operations_image
from tests.support.runtime import run_role


def test_cold_restore_job_carries_mode_and_refuses_an_image_without_the_role(tmp_path):
    resources, variables = api.scenario_objects()
    variables.update(
        shared_data_action="submit",
        shared_data_job_action="restore",
        shared_data_recovery_mode=True,
        shared_data_image=operations_image(native=False),
        shared_data_job_timeout=60,
    )
    with api.maintenance_api(tmp_path, resources) as (connection, state):
        state["job_created"] = lambda job, state: job.update(status={"succeeded": 1})
        result = run_role(tmp_path, "shared_data", "main", {**connection, **variables})
        assert result.returncode == 0, result.stdout + result.stderr
        [job] = [r for r in state["objects"].values() if r["kind"] == "Job"]
        container = job["spec"]["template"]["spec"]["containers"][0]
        assert json.loads(container["args"][-1])["shared_data_recovery_mode"] is True
        assert container["command"][:2] == ["/bin/sh", "-ec"]
        denied = subprocess.run(
            container["command"] + container["args"],
            env={"PATH": str(tmp_path)},
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert denied.returncode != 0
        assert "ansible" not in denied.stderr
