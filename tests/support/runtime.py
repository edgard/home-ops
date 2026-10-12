"""Shared isolated execution boundaries for real roles and native tools."""

import importlib.util
import os
import signal
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"
PLAYBOOK = ROOT / ".venv/bin/ansible-playbook"


def load_module(relative):
    path = ROOT / "ansible/roles" / relative
    name = relative.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment(directory, extra=None):
    # Allow only process/tool basics: never inherit operator credentials or config.
    allowed = {
        "PATH",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SYSTEMROOT",
        "WINDIR",
        "USER",
        "LOGNAME",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed}
    directory = Path(directory)
    env.update(
        HOME=str(directory),
        NO_PROXY="127.0.0.1,localhost",
        PYTHONDONTWRITEBYTECODE="1",
        PATH=str(directory) + os.pathsep + os.environ["PATH"],
        ANSIBLE_CONFIG=str(ROOT / "ansible.cfg"),
        ANSIBLE_ROLES_PATH=str(ROOT / "ansible/roles"),
        ANSIBLE_COLLECTIONS_PATH=str(ROOT / ".ansible/collections"),
        ANSIBLE_PYTHON_INTERPRETER=str(PYTHON),
        ANSIBLE_LOCAL_TEMP=str(directory / ".ansible/tmp"),
        ANSIBLE_NOCOLOR="1",
    )
    env.update(extra or {})
    return env


def run_role(
    directory,
    role,
    entry,
    variables=None,
    *,
    check=False,
    env=None,
    after=None,
    rescue=None,
    timeout=90,
):
    directory = Path(directory)
    tasks = [
        {
            "name": "Load shared operator filters",
            "ansible.builtin.import_role": {"name": "operator_secrets", "tasks_from": "validate"},
            "when": False,
        },
        {
            "name": "Exercise real role",
            "ansible.builtin.include_role": {"name": role, "tasks_from": entry},
        },
    ] + (after or [])
    if rescue:
        tasks = [
            tasks[0],
            {"name": "Observe isolated role failure", "block": tasks[1:], "rescue": rescue},
        ]
    variables = {
        "repo_root": str(ROOT),
        "ansible_python_interpreter": str(PYTHON),
        **(variables or {}),
    }
    play = directory / "role.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "Isolated role scenario",
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": variables,
                    "tasks": tasks,
                }
            ],
            sort_keys=False,
        )
    )
    args = [str(PLAYBOOK), str(play), *(["--check"] if check else [])]
    process = subprocess.Popen(
        args,
        cwd=ROOT,
        env=environment(directory, env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise


def executable(directory, name, source):
    path = Path(directory) / name
    path.write_text(f"#!{sys.executable}\n" + source)
    path.chmod(0o700)
    return path
