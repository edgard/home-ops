import json
import os
import subprocess
import sys
from tests.support.runtime import ROOT, environment
from tests.support.sources import read_yaml

PROJECT = "12345678-1234-1234-1234-123456789abc"
ARGS = [
    "--color",
    "no",
    "--server-url",
    "https://vault.bitwarden.com",
    "secret",
    "list",
    PROJECT,
    "--output",
    "json",
]


def test_real_secretspec_scope_and_multiline_preservation(tmp_path):
    import shutil

    binary = shutil.which("secretspec")
    assert binary is not None, "Install pinned SecretSpec for the integration check"
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=True
    ).stdout.strip()
    pin = read_yaml(ROOT / "ansible/roles/cli_secrets/defaults/main.yml")[
        "cli_secrets_secretspec_version"
    ]
    assert version == "secretspec " + pin
    value = 'line one\n$(ignored) `literal` "quotes"\n'
    path = tmp_path
    manifest = path / "secretspec.toml"
    manifest.write_text(
        f'[project]\nname = "home-ops-fixture"\nrevision = "1.0"\n[providers]\napp = {{ uri = "bws://{PROJECT}", credentials = {{ access_token = {{ provider = "env", ref = {{ item = "FIXTURE_TOKEN" }} }} }} }}\n[profiles.default]\nVISIBLE = {{ description = "Visible fixture", required = true, providers = ["app"], ref = {{ item = "value" }} }}\nHIDDEN = {{ description = "Excluded fixture", required = true, providers = ["app"], ref = {{ item = "absent" }} }}\n[scopes.test]\nsecrets = ["VISIBLE"]\n'
    )
    bws = path / "bws"
    bws.write_text('#!/usr/bin/env python3\nimport os\nprint(os.environ["FIXTURE_JSON"])\n')
    bws.chmod(493)
    env = environment(
        path,
        dict(
            FIXTURE_TOKEN="synthetic",
            FIXTURE_JSON=json.dumps([{"id": "1", "key": "value", "value": value}]),
            HIDDEN="stale",
            PATH=str(path) + os.pathsep + os.environ["PATH"],
            SECRETSPEC_BWS_CLI_PATH=str(
                ROOT / "ansible/roles/cli_secrets/files/bws_readonly.py"
            ),
        ),
    )
    child = [
        sys.executable,
        "-c",
        'import json,os; print(json.dumps({"value":os.environ["VISIBLE"],"hidden":"HIDDEN" in os.environ}))',
    ]
    result = subprocess.run(
        [
            binary,
            "run",
            "--file",
            str(manifest),
            "--profile",
            "default",
            "--scope",
            "test",
            "--reason",
            "Synthetic CI integration",
            "--",
            *child,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"value": value, "hidden": False}
    env["FIXTURE_JSON"] = json.dumps(
        [
            {"id": "1", "key": "value", "value": "PRIVATE"},
            {"id": "2", "key": "value", "value": "PRIVATE"},
        ]
    )
    result = subprocess.run(
        [
            binary,
            "run",
            "--file",
            str(manifest),
            "--profile",
            "default",
            "--scope",
            "test",
            "--reason",
            "Synthetic duplicate test",
            "--",
            *child,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "PRIVATE" not in result.stdout + result.stderr
    assert "duplicate-names" in result.stderr
    env["FIXTURE_JSON"] = json.dumps([{"id": "1", "key": "value", "value": value}])
    env["FIXTURE_TOKEN"] = ""
    env["BWS_ACCESS_TOKEN"] = "PRIVATE_FALLBACK"
    result = subprocess.run(
        [
            binary,
            "check",
            "--file",
            str(manifest),
            "--profile",
            "default",
            "--scope",
            "test",
            "--reason",
            "Synthetic empty credential test",
            "--no-prompt",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "PRIVATE_FALLBACK" not in result.stdout + result.stderr
