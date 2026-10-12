import hashlib
import io
import json
import stat
import subprocess
import tarfile
import zipfile

import pytest

from tests.support.runtime import run_role, ROOT, executable
from tests.support.sources import read_yaml


def test_selected_default_installation_and_checksum_failure(tmp_path):
    catalog = {}
    for name, suffix in [("secretspec", ".tar.xz"), ("bws", ".zip")]:
        content = ('#!/bin/sh\nprintf "%s\\n" "' + name + ' fixture"\n').encode()
        archive = tmp_path / (name + suffix)
        if suffix == ".zip":
            with zipfile.ZipFile(archive, "w") as file:
                file.writestr(name, content)
        else:
            with tarfile.open(archive, "w:xz") as file:
                member = tarfile.TarInfo(name)
                member.mode, member.size = 0o755, len(content)
                file.addfile(member, io.BytesIO(content))
        checksum = tmp_path / (name + ".sha256")
        checksum.write_text(
            hashlib.sha256(archive.read_bytes()).hexdigest()
            + ("  " + archive.name if name == "bws" else "")
            + "\n"
        )
        catalog[name] = {"url": archive.as_uri(), "checksum": checksum.as_uri()}
    variables = {
        "operator_secrets_tools_directory": str(tmp_path / "bin"),
        "operator_secrets_tools_catalog": catalog,
    }
    result = run_role(
        tmp_path,
        "operator_secrets",
        "setup",
        {**variables, "operator_secrets_install_tools": ["secretspec"]},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    binary = tmp_path / "bin/secretspec"
    original = binary.read_bytes()
    assert not (tmp_path / "bin/bws").exists()
    result = run_role(tmp_path, "operator_secrets", "setup", variables)
    assert result.returncode == 0, result.stdout + result.stderr
    assert binary.read_bytes() == original
    for name in ["secretspec", "bws"]:
        path = tmp_path / "bin" / name
        assert stat.S_IMODE(path.stat().st_mode) == 0o755
        assert subprocess.check_output([str(path)], text=True).strip() == name + " fixture"
    (tmp_path / "secretspec.sha256").write_text("0" * 64 + "\n")
    stage = tmp_path / "stage.json"
    after = [
        {
            "name": "Export staging location",
            "ansible.builtin.copy": {
                "dest": str(stage),
                "content": "{{ operator_secrets_tool_temp.path | to_json }}",
                "mode": "0600",
            },
        }
    ]
    result = run_role(
        tmp_path,
        "operator_secrets",
        "setup",
        {**variables, "operator_secrets_install_tools": ["secretspec"]},
        rescue=after
        + [
            {
                "name": "Propagate native checksum failure",
                "ansible.builtin.fail": {"msg": "{{ ansible_failed_result.msg }}"},
            }
        ],
    )
    assert result.returncode != 0 and "checksum" in result.stdout + result.stderr
    assert binary.read_bytes() == original
    from pathlib import Path

    assert not Path(json.loads(stage.read_text())).exists()


@pytest.mark.parametrize("version", ["expected", "older"])
def test_operator_tool_pin_validation(tmp_path, version):
    defaults = read_yaml(ROOT / "ansible/roles/operator_secrets/defaults/main.yml")
    pin = defaults["operator_secrets_secretspec_version"]
    executable(
        tmp_path,
        "secretspec",
        "print('secretspec " + (pin if version == "expected" else "0.0.1") + "')\n",
    )
    executable(tmp_path, "bws", "print('bws " + defaults["operator_secrets_bws_version"] + "')\n")
    result = run_role(tmp_path, "operator_secrets", "validate")
    assert (result.returncode == 0) == (version == "expected"), result.stdout + result.stderr
