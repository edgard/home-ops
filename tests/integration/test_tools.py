import pytest

from tests.support.runtime import run_role, ROOT, executable


@pytest.mark.parametrize("version", ["expected", "older"])
def test_operator_tool_pin_validation(tmp_path, version):
    pin = (ROOT / ".secretspec-version").read_text().strip()
    executable(
        tmp_path,
        "secretspec",
        "print('secretspec " + (pin if version == "expected" else "0.0.1") + "')\n",
    )
    executable(tmp_path, "bws", "print('bws 2.1.0')\n")
    result = run_role(tmp_path, "operator_secrets", "validate")
    assert (result.returncode == 0) == (version == "expected"), result.stdout + result.stderr
