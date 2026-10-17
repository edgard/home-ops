import subprocess

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import PLAYBOOK, ROOT, environment, executable, run_role
from tests.support.sources import read_yaml
from tests.support.talos import MATERIAL


def test_cluster_preflight_denial_precedes_node_mutation(tmp_path):
    pin = read_yaml(ROOT / "ansible/roles/cli_secrets/defaults/main.yml")[
        "cli_secrets_secretspec_version"
    ]
    executable(
        tmp_path,
        "secretspec",
        "print('secretspec " + pin + "')\n",
    )
    executable(
        tmp_path,
        "bws",
        "import sys\nif sys.argv[1:]==['--version']: print('bws 2.1.0')\nelse: print('PRIVATE_PROVIDER_ERROR',file=sys.stderr);sys.exit(1)\n",
    )
    marker = tmp_path / "node-contact"
    for name in ["talosctl", "helm"]:
        executable(
            tmp_path,
            name,
            f"import pathlib,sys\nif sys.argv[1] not in ['version','--version']:pathlib.Path({str(marker)!r}).touch()\nprint('synthetic-version')\n",
        )
    result = subprocess.run(
        [str(PLAYBOOK), "ansible/playbooks/cluster-create.yml"],
        cwd=ROOT,
        env=environment(
            tmp_path,
            {
                "TALOS_NODE": "192.0.2.10",
                "TALOS_CLUSTER_NAME": "fixture",
                "TALOS_INSTALL_DISK": "/dev/fixture",
                "TALOS_SECRETS_YAML": MATERIAL,
                "ESO_BWS_ACCESS_TOKEN": "synthetic-token",
            },
        ),
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode != 0
    assert not marker.exists()
    assert "PRIVATE_PROVIDER_ERROR" not in result.stdout + result.stderr
    assert "Application credential validation failed" in result.stdout


@pytest.mark.parametrize(
    "app,check", [("", False), ("one", False), ("missing", False), ("one", True)]
)
def test_argo_refresh_scope(tmp_path, app, check):
    prefix = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/"
    objects = {
        prefix + name: {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {"name": name, "namespace": "argocd"},
            "spec": {},
        }
        for name in ["one", "two"]
    }
    with cluster_api(tmp_path, {"objects": objects, "events": []}) as (
        connection,
        observed,
    ):
        result = run_role(
            tmp_path, "argocd", "refresh", {**connection, "app": app}, check=check
        )
        state = observed()
    assert (result.returncode == 0) == (app != "missing"), result.stdout + result.stderr
    patched = [event for event in state["events"] if event["method"] == "PATCH"]
    assert {event["path"] for event in patched} == (
        set()
        if app == "missing"
        else {prefix + name for name in ([app] if app else ["one", "two"])}
    )
    if check:
        assert all(event["query"].get("dryRun") == ["All"] for event in patched)
        assert state["objects"] == objects
    assert all(
        event["body"]["metadata"]["annotations"]["argocd.argoproj.io/refresh"] == "hard"
        for event in patched
    )


@pytest.mark.parametrize("failure", ["", "create", "cleanup"])
def test_warmup_cleanup_matches_created_pod(tmp_path, failure):
    defaults = read_yaml(ROOT / "ansible/roles/platform/defaults/main.yml")
    path = (
        "/api/v1/namespaces/kube-system/pods/"
        + defaults["platform_k8tz_warmup_pod_name"]
    )
    state = {"objects": {}, "events": [], "allowed_creates": [path]}
    if failure:
        state["failure"] = {
            "method": "POST" if failure == "create" else "DELETE",
            "path": "/pods",
            **({"after": "POST"} if failure == "cleanup" else {}),
        }
    with cluster_api(tmp_path, state) as (connection, observed):
        result = run_role(
            tmp_path,
            "platform",
            "k8tz_warmup",
            {**connection, "platform_wait_default_delay": 0},
        )
        state = observed()
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    creates = [event for event in state["events"] if event["method"] == "POST"]
    assert len(creates) == 1
    assert creates[0]["body"]["metadata"] == {
        "name": defaults["platform_k8tz_warmup_pod_name"],
        "namespace": "kube-system",
    }
    deletes = [event for event in state["events"] if event["method"] == "DELETE"]
    if failure != "create":
        assert deletes[-1]["path"] == path
    assert (path in state["objects"]) == (failure == "cleanup")


@pytest.mark.parametrize("failure", ["", "api", "timeout"])
def test_platform_wait_propagates_failure(tmp_path, failure):
    path = "/api/v1/namespaces/fixture/pods/ready"
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "ready", "namespace": "fixture"},
        "status": {
            "conditions": [
                {"type": "Ready", "status": "False" if failure == "timeout" else "True"}
            ]
        },
    }
    state = {"objects": {path: pod}, "events": []}
    if failure == "api":
        state["failure"] = {"method": "GET", "path": path}
    with cluster_api(tmp_path, state) as (connection, observed):
        result = run_role(
            tmp_path,
            "platform",
            "wait_condition",
            {
                **connection,
                "platform_wait_api_version": "v1",
                "platform_wait_kind": "Pod",
                "platform_wait_name": "ready",
                "platform_wait_namespace": "fixture",
                "platform_wait_condition_type": "Ready",
                "platform_wait_retries": 1,
                "platform_wait_delay": 1,
            },
        )
        events = observed()["events"]
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    assert events and all(
        event["method"] == "GET" and event["path"] == path for event in events
    )
