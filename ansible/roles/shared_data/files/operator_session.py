"""Serialize a bounded named operation inside one immutable live operator Pod."""

import fcntl
import json
import os
import subprocess
import sys

ALLOWED = {
    "shared_data_action",
    "shared_data_confirm",
    "shared_data_operator_step",
    "shared_data_operation_id",
    "shared_data_operation_kind",
    "shared_data_apps",
    "shared_data_image",
    "shared_data_lease_duration",
    "shared_data_holder_pod_uid",
    "shared_data_enrollment_proof",
    "shared_data_enrollment_budget",
    "shared_data_wait_retries",
    "shared_data_wait_delay",
}
STEPS = {"hold", "prepare", "renew", "enroll", "apply", "resume", "abort"}


def main(payload):
    values = json.loads(payload)
    if set(values) - ALLOWED or values.get("shared_data_operator_step") not in STEPS:
        raise ValueError(
            "only named operator operations and nonsecret inputs are accepted"
        )
    if (
        values.get("shared_data_action") != "operator_execute"
        or values.get("shared_data_confirm") is not True
    ):
        raise ValueError("confirmed operator execution required")
    if values.get("shared_data_holder_pod_uid") != os.environ.get("POD_UID"):
        raise ValueError("must execute inside the original immutable actor")
    with open("/tmp/shared-data-operator.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            [
                "ansible-playbook",
                "ansible/playbooks/shared-data.yml",
                "--extra-vars",
                json.dumps(values),
            ],
            timeout=7200,
            check=False,
        )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
