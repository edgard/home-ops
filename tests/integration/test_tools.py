import pytest

from tests.support.runtime import run_role, ROOT, executable
from tests.support.sources import read_yaml


@pytest.mark.parametrize("version", ["expected", "older"])
def test_cli_tool_pin_validation(tmp_path, version):
    pin = read_yaml(ROOT / "ansible/roles/cli_secrets/defaults/main.yml")[
        "cli_secrets_secretspec_version"
    ]
    executable(
        tmp_path,
        "secretspec",
        "print('secretspec " + (pin if version == "expected" else "0.0.1") + "')\n",
    )
    executable(tmp_path, "bws", "print('bws 2.1.0')\n")
    result = run_role(tmp_path, "cli_secrets", "validate")
    assert (result.returncode == 0) == (version == "expected"), result.stdout + result.stderr
