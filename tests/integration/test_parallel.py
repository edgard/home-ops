import json
import subprocess
import time
from pathlib import Path

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import PYTHON, ROOT, environment, run_command


@pytest.mark.parametrize("workers", [0, 4])
@pytest.mark.parametrize(
    "scenario", ["success", "tool-failure", "incomplete", "terminated"]
)
def test_render_fixture_coordinates_consumers(tmp_path, workers, scenario):
    (tmp_path / "scenario").write_text(scenario)
    (tmp_path / "conftest.py").write_text("""import json
import os
from pathlib import Path
import subprocess
import time
import pytest
import tests.config.kubernetes.conftest as fixtures
from tests.support.runtime import ROOT

rendered = fixtures.rendered
base = Path(__file__).parent

@pytest.fixture(scope="session")
def repo_root():
    return ROOT

@pytest.fixture(scope="session", autouse=True)
def prepare(worker_id):
    (base / (worker_id + ".ready")).touch()
    count = int((base / "workers").read_text()) or 1
    deadline = time.monotonic() + 15
    while len(list(base.glob("*.ready"))) < count:
        assert time.monotonic() < deadline, "consumers did not start"
        time.sleep(0.02)
    def render(root, output):
        with (base / "calls.jsonl").open("a") as stream:
            stream.write(json.dumps(str(output)) + "\\n")
        assert output.stat().st_mode & 0o777 == 0o700
        scenario = (base / "scenario").read_text()
        apps = fixtures.applications(root)
        for app in apps[:-1] if scenario == "incomplete" else apps:
            target = output / "rendered" / app.category / (app.name + ".yaml")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("kind: ConfigMap\\nmetadata: {name: fixture}\\n")
        if scenario == "tool-failure":
            error = subprocess.CalledProcessError(1, ["helm", "template"])
            error.add_note("synthetic native diagnostic")
            raise error
        if scenario == "terminated":
            os._exit(17)
    fixtures.render_validate = render
""")
    (tmp_path / "workers").write_text(str(workers))
    for index in range(4):
        (tmp_path / f"test_consumer_{index}.py").write_text("""import pytest

@pytest.mark.parametrize("case", [0, 1])
def test_documents(rendered, worker_id, case):
    assert rendered and all(doc["kind"] == "ConfigMap" for doc in rendered)
    assert rendered[0].get("owner", worker_id) == worker_id
    rendered[0]["owner"] = worker_id
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
            "-n",
            str(workers),
            "--dist=worksteal",
            "--basetemp",
            str(tmp_path / "run"),
            "--junitxml",
            str(tmp_path / "report.xml"),
            str(tmp_path),
            "-q",
        ],
        cwd=tmp_path,
        env=environment(tmp_path, {"PYTHONPATH": str(ROOT)}),
        timeout=60,
    )
    output = result.stdout + result.stderr
    calls = [
        json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()
    ]
    assert len(calls) == 1, output
    if scenario != "terminated":
        assert all(not Path(path).exists() for path in calls), "render workspace leaked"
    if scenario == "success":
        assert result.returncode == 0, output
        assert "8 passed" in output
        snapshots = list((tmp_path / "run").rglob("rendered.json"))
        assert len(snapshots) == 1
        assert "owner" not in snapshots[0].read_text(), (
            "worker mutated shared documents"
        )
        assert snapshots[0].stat().st_mode & 0o777 == 0o600
    else:
        assert result.returncode != 0, output
        if scenario == "terminated" and workers == 0:
            assert result.returncode == 17
            return
        assert "8 errors" in output if scenario != "terminated" else "failed" in output
        diagnostic = (
            "synthetic native diagnostic"
            if scenario == "tool-failure"
            else (
                "rendered application inventory"
                if scenario == "incomplete"
                else "interrupted before publication"
            )
        )
        assert diagnostic in output
        assert not list((tmp_path / "run").rglob("rendered.json"))


@pytest.mark.parametrize("failure", [TimeoutError, KeyboardInterrupt])
def test_command_failure_terminates_child_processes(tmp_path, failure, monkeypatch):
    pid_file = tmp_path / "child.pid"
    original = subprocess.Popen.communicate
    interrupted = False

    def interrupt(process, *args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            deadline = time.monotonic() + 5
            while not pid_file.exists():
                assert time.monotonic() < deadline
                time.sleep(0.02)
            interrupted = True
            raise failure()
        return original(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "communicate", interrupt)
    source = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        f"Path({str(pid_file)!r}).write_text(str(child.pid)); time.sleep(60)"
    )
    with pytest.raises(failure):
        run_command([str(PYTHON), "-c", source])
    pid = int(pid_file.read_text())
    # A killed child may briefly remain a zombie until the OS reaps it.
    deadline = time.monotonic() + 5
    while True:
        status = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if status.returncode != 0 or status.stdout.strip().startswith("Z"):
            break
        assert time.monotonic() < deadline, "child process survived termination"
        time.sleep(0.02)


def test_loopback_apis_have_independent_ports_and_cleanup(tmp_path):
    import urllib.request

    connections = []
    for name in ("first", "second"):
        (tmp_path / name).mkdir()
    with cluster_api(tmp_path / "first", {"objects": {}, "events": []}) as (first, _):
        with cluster_api(tmp_path / "second", {"objects": {}, "events": []}) as (
            second,
            _,
        ):
            from tests.support.sources import read_yaml

            connections = [
                read_yaml(item["kubeconfig_path"])["clusters"][0]["cluster"]["server"]
                for item in (first, second)
            ]
            assert len(set(connections)) == 2
            for url in connections:
                with urllib.request.urlopen(url + "/version", timeout=2) as response:
                    assert response.status == 200
    for url in connections:
        with pytest.raises(OSError):
            urllib.request.urlopen(url + "/version", timeout=2)
