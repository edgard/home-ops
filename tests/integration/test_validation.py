"""Exercise the public validation commands through Task's real CLI."""

import json
import shutil

import pytest

from tests.support.runtime import ROOT, environment, executable, run_command


def task_project(tmp_path):
    shutil.copyfile(ROOT / "Taskfile.yaml", tmp_path / "Taskfile.yaml")
    return tmp_path


def test_task_discovers_new_directories_and_forwards_pytest_arguments(tmp_path):
    task_project(tmp_path)
    (tmp_path / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
    )
    tests = tmp_path / "tests/new_category"
    tests.mkdir(parents=True)
    (tests / "test_example.py").write_text(
        "def test_alpha(): pass\ndef test_beta(): pass\n"
    )
    env = environment(tmp_path)
    full = run_command(["task", "test"], cwd=tmp_path, env=env)
    assert full.returncode == 0, full.stdout + full.stderr
    assert "2 passed" in full.stdout
    report = tmp_path / "result with spaces.xml"
    focused = run_command(
        [
            "task",
            "test",
            "--",
            "tests/new_category",
            "-k",
            "alpha",
            "--junitxml=" + str(report),
        ],
        cwd=tmp_path,
        env=env,
    )
    assert focused.returncode == 0, focused.stdout + focused.stderr
    assert "1 passed" in focused.stdout and "1 deselected" in focused.stdout
    assert report.is_file()


@pytest.mark.parametrize("failure", ["yamlfmt", "yamllint", "pytest", None])
def test_complete_gate_propagates_failures_without_reaching_tests_early(
    tmp_path, failure
):
    task_project(tmp_path)
    tools = tmp_path / ".venv/bin"
    tools.mkdir(parents=True)
    record = tmp_path / "commands.jsonl"
    stub = """import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
kind='pytest' if name=='python' and sys.argv[1:3]==['-m','pytest'] else name
with pathlib.Path(os.environ['FIXTURE_RECORD']).open('a') as output:
 output.write(json.dumps({'tool':kind,'args':sys.argv[1:]})+'\\n')
raise SystemExit(17 if os.environ.get('FIXTURE_FAIL')==kind else 0)
"""
    for name in [
        "python",
        "ruff",
        "yamllint",
        "check-jsonschema",
        "ansible-lint",
        "ansible-playbook",
    ]:
        executable(tools, name, stub)
    for name in ["yamlfmt", "tofu", "actionlint", "shellcheck", "uv"]:
        executable(tmp_path, name, stub)
    (tmp_path / "terraform").mkdir()
    actions = tmp_path / ".github/actions/fixture"
    actions.mkdir(parents=True)
    (actions / "action.yml").write_text("name: fixture\n")
    result = run_command(
        ["task", "check"],
        cwd=tmp_path,
        env=environment(
            tmp_path, {"FIXTURE_RECORD": str(record), "FIXTURE_FAIL": failure or ""}
        ),
    )
    assert (result.returncode == 0) == (failure is None), result.stdout + result.stderr
    commands = [json.loads(line) for line in record.read_text().splitlines()]
    reached_pytest = [command for command in commands if command["tool"] == "pytest"]
    assert len(reached_pytest) == (0 if failure in ["yamlfmt", "yamllint"] else 1)
    for command in commands:
        assert "--fix" not in command["args"] and "--write" not in command["args"]
        if command["tool"] == "uv":
            assert "sync" not in command["args"], (
                "Checking must not install dependencies"
            )


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped"])
def test_quality_gate_rejects_unsuccessful_dependencies(tmp_path, result):
    from tests.support.sources import read_yaml

    gate = read_yaml(ROOT / ".github/workflows/ci.yml")["jobs"]["quality-gate"]
    step = gate["steps"][0]
    outcomes = {
        "format": {"result": "success"},
        "lint": {"result": result},
        "tests": {"result": "success"},
    }
    executed = run_command(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=ROOT,
        env=environment(tmp_path, {"JOB_RESULTS": json.dumps(outcomes)}),
    )
    assert (executed.returncode == 0) == (result == "success"), (
        executed.stdout + executed.stderr
    )


@pytest.mark.parametrize("entry", ["argo:sync", "restic:restore", "restic:restore-all"])
def test_operator_extra_variables_preserve_literal_argument_values(tmp_path, entry):
    record = tmp_path / "arguments.json"
    playbook = executable(
        tmp_path,
        "ansible-playbook",
        "import json,os,pathlib,sys\npathlib.Path(os.environ['FIXTURE_RECORD']).write_text(json.dumps(sys.argv[1:]))\n",
    )
    value = "space with 'quotes' and $literal and $(printf expanded)"
    result = run_command(
        [
            "task",
            entry,
            "ANSIBLE_PLAYBOOK=" + str(playbook),
            "app=" + value,
            "snapshot=" + value,
        ],
        cwd=ROOT,
        env=environment(tmp_path, {"FIXTURE_RECORD": str(record)}),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    args = json.loads(record.read_text())
    delivered = json.loads(args[args.index("--extra-vars") + 1])
    if entry == "argo:sync":
        assert delivered == {"app": value}
    else:
        assert delivered["restic_restore_snapshot"] == value
        assert str(delivered["restic_restore_confirm"]).lower() == "false"
        assert delivered["restic_restore_mode"] == (
            "all" if entry.endswith("-all") else "app"
        )
        if entry == "restic:restore":
            assert delivered["restic_restore_app"] == value
