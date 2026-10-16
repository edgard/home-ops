import os
import json
import subprocess
import pytest
from tests.support.runtime import ROOT, environment


@pytest.mark.parametrize(
    "task,scope,playbook",
    [
        ("secrets:check", "talos", None),
        ("tf:plan", "terraform", "terraform-plan.yml"),
        ("tf:apply", "terraform", "terraform-apply.yml"),
        ("talos:gen", "talos", "talos-generate.yml"),
        ("cluster:create", "cluster", "cluster-create.yml"),
        ("platform:create", "platform", "platform-bootstrap.yml"),
        ("secrets:sync-cluster-token", "platform", "secrets-sync-cluster-token.yml"),
    ],
)
def test_task_clears_inherited_credentials_and_preserves_local_settings(
    tmp_path, task, scope, playbook
):
    path = tmp_path
    record = path / "record.json"
    stub = path / "secretspec"
    stub.write_text(
        "#!/usr/bin/env python3\nimport json,os,pathlib,sys\npathlib.Path(os.environ['FIXTURE_RECORD']).write_text(json.dumps({'environment':dict(os.environ),'args':sys.argv[1:]}))\n"
    )
    stub.chmod(493)
    validator = path / "ansible-playbook"
    validator.write_text("#!/bin/sh\nexit 0\n")
    validator.chmod(493)
    stale = {
        "BWS_ACCESS_TOKEN": "PRIVATE",
        "BW_ACCESS_TOKEN": "PRIVATE",
        "AWS_ACCESS_KEY_ID": "PRIVATE",
        "AWS_SECRET_ACCESS_KEY": "PRIVATE",
        "AWS_SESSION_TOKEN": "PRIVATE",
        "TF_VAR_cloudflare_api_token": "PRIVATE",
        "TF_CLI_ARGS_plan": "PRIVATE",
        "ANSIBLE_VAULT_PASSWORD_FILE": "PRIVATE",
        "SECRETSPEC_PROVIDER": "env",
        "TALOS_SECRETS_YAML": "PRIVATE",
        "ESO_BWS_ACCESS_TOKEN": "PRIVATE",
    }
    env = environment(path, stale)
    env.update(
        HOME=str(path),
        PATH=str(path) + os.pathsep + os.environ["PATH"],
        TALOS_NODE="192.0.2.10",
        TALOS_INSTALL_DISK="/dev/fixture",
        TALOSCONFIG="custom path/config",
        FIXTURE_RECORD=str(record),
    )
    result = subprocess.run(
        [
            "task",
            task,
            *(["scope=talos"] if task == "secrets:check" else []),
            "ANSIBLE_PLAYBOOK=" + str(validator),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    delivered = json.loads(record.read_text())
    assert all((name not in delivered["environment"] for name in stale))
    assert delivered["environment"]["TALOS_NODE"] == "192.0.2.10"
    assert delivered["environment"]["TALOSCONFIG"] == "custom path/config"
    assert delivered["args"][delivered["args"].index("--scope") + 1] == scope
    assert delivered["environment"]["SECRETSPEC_BWS_CLI_PATH"] == str(
        ROOT / "ansible/roles/cli_secrets/files/bws_readonly.py"
    )
    if playbook:
        assert delivered["args"][-2:] == [
            str(validator),
            str(ROOT / "ansible/playbooks" / playbook),
        ]
    assert "PRIVATE" not in " ".join(delivered["args"])
    record.unlink()
    validator.write_text("#!/bin/sh\nexit 1\n")
    result = subprocess.run(
        [
            "task",
            task,
            *(["scope=talos"] if task == "secrets:check" else []),
            "ANSIBLE_PLAYBOOK=" + str(validator),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert not record.exists(), "A failed Ansible preflight must prevent SecretSpec invocation"
