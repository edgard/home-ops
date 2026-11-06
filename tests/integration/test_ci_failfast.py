"""Exercise the workflow's real pytest arguments against bounded synthetic work."""

import json
import shlex

import pytest
import yaml

from tests.support.runtime import PYTHON, ROOT, environment, run_command


@pytest.mark.parametrize("failure", [False, True])
def test_ci_stops_queued_work_after_failure_and_runs_every_case_on_success(
    tmp_path, failure
):
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    command = next(
        step["run"]
        for step in workflow["jobs"]["tests"]["steps"]
        if step.get("run", "").startswith("task test -- ")
    )
    report = tmp_path / "report.xml"
    args = [
        "--junitxml=" + str(report) if arg.startswith("--junitxml=") else arg
        for arg in shlex.split(command)[3:]
    ]
    (tmp_path / "failure.json").write_text(json.dumps(failure))
    (tmp_path / "test_work.py").write_text("""import json
from pathlib import Path
import time
import pytest

base = Path(__file__).parent

def test_00_first():
    if not json.loads((base / "failure.json").read_text()):
        return
    deadline = time.monotonic() + 10
    while not (base / "started").exists():
        assert time.monotonic() < deadline, "other worker did not start"
        time.sleep(0.01)
    raise AssertionError("visible synthetic failure")

@pytest.mark.parametrize("case", range(24))
def test_10_remaining(case):
    with (base / "started").open("a") as stream:
        stream.write(str(case) + "\\n")
    time.sleep(0.2)
""")
    result = run_command(
        [
            str(PYTHON),
            "-m",
            "pytest",
            "-c",
            str(ROOT / "pyproject.toml"),
            "--confcutdir",
            str(tmp_path),
            "--basetemp",
            str(tmp_path / "run"),
            "-o",
            "cache_dir=" + str(tmp_path / "cache"),
            *args,
            str(tmp_path / "test_work.py"),
        ],
        cwd=tmp_path,
        env=environment(tmp_path),
        timeout=40,
    )
    output = result.stdout + result.stderr
    assert report.is_file(), output
    started = (tmp_path / "started").read_text().splitlines()
    if failure:
        assert result.returncode in (1, 2), output
        assert "visible synthetic failure" in output
        assert len(started) <= 4, (
            f"Unrelated queued cases kept running: {len(started)}\n{output}"
        )
    else:
        assert result.returncode == 0, output
        assert sorted(map(int, started)) == list(range(24)), output
        assert "25 passed" in output
