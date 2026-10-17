"""Lifecycle for the small, synthetic loopback Kubernetes fixture."""

import json
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import yaml

from tests.support.runtime import PYTHON, environment


@contextmanager
def cluster_api(directory, state):
    directory = Path(directory)
    state_file = directory / "api-state.json"
    if "objects" in state:
        state.setdefault("allowed_creates", list(state["objects"]))
    state_file.write_text(json.dumps(state))
    process = subprocess.Popen(
        [str(PYTHON), str(Path(__file__).with_name("cluster_api.py")), str(directory)],
        env=environment(directory),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        port = directory / "api-port"
        while not port.exists():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "loopback API did not start"
            time.sleep(0.02)
        kubeconfig = directory / "kubeconfig"
        kubeconfig.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "v1",
                    "kind": "Config",
                    "clusters": [
                        {
                            "name": "fixture",
                            "cluster": {
                                "server": "http://127.0.0.1:" + port.read_text()
                            },
                        }
                    ],
                    "contexts": [
                        {
                            "name": "fixture",
                            "context": {"cluster": "fixture", "user": "fixture"},
                        }
                    ],
                    "users": [{"name": "fixture", "user": {}}],
                    "current-context": "fixture",
                }
            )
        )
        kubeconfig.chmod(0o600)
        yield (
            {"kubeconfig_path": str(kubeconfig), "kube_context": "fixture"},
            lambda: json.loads(state_file.read_text()),
        )
    finally:
        (directory / "api-stop").touch()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()


def pod_exec_collection(directory):
    """Use real collection files with one isolated module override."""
    from tests.support.runtime import ROOT

    source = ROOT / ".ansible/collections/ansible_collections/kubernetes/core"
    target = Path(directory) / "collections/ansible_collections/kubernetes/core"
    (target / "plugins/modules").mkdir(parents=True)
    for path in source.iterdir():
        if path.name != "plugins":
            (target / path.name).symlink_to(path, target_is_directory=path.is_dir())
    for path in (source / "plugins").iterdir():
        if path.name != "modules":
            (target / "plugins" / path.name).symlink_to(
                path, target_is_directory=path.is_dir()
            )
    for path in (source / "plugins/modules").iterdir():
        if path.name != "k8s_exec.py":
            (target / "plugins/modules" / path.name).symlink_to(
                path, target_is_directory=path.is_dir()
            )
    (target / "plugins/modules/k8s_exec.py").write_text(
        Path(__file__).with_name("exec_module.py").read_text()
    )
    return (
        str(Path(directory) / "collections") + ":" + str(ROOT / ".ansible/collections")
    )
