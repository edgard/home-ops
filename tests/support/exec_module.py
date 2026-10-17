"""Only the unavailable pod websocket boundary is replaced; commands never run."""

import json
import os
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

module = AnsibleModule(
    argument_spec={
        name: {"type": "str"}
        for name in ["kubeconfig", "context", "namespace", "pod", "command"]
    },
    supports_check_mode=True,
)
root = Path(os.environ["EXEC_STATE"])
state = json.loads(root.read_text())
params = module.params
assert params["namespace"] == "selfhosted" and params["pod"] == "restore-pod"
command = params["command"]
assert command.startswith(("sh -ceu ", "restic --retry-lock ")), command
state["events"].append(
    {
        "method": "EXEC",
        "path": params["namespace"] + "/" + params["pod"],
        "body": command,
    }
)
root.write_text(json.dumps(state))
if os.environ.get("EXEC_FAIL") and command.startswith(os.environ["EXEC_FAIL"]):
    module.fail_json(msg="synthetic exec failure", rc=1)
module.exit_json(changed=True, rc=0, stdout="", stderr="")
