"""Actual platform role, actual Helm renders, only Kubernetes is synthetic."""

import json

import pytest
import yaml

from tests.integration import test_data_maintenance as api
from tests.integration.cold_bootstrap.support import (
    IMAGE,
    extend_api,
    git_boundary,
    infrastructure_objects,
    start_job_workers,
)
from tests.support.runtime import ROOT, load_module, run_role

TOKEN = "c" * 32
REVISION = "a" * 40


def variables(connection, apps=None):
    registry = yaml.safe_load(
        (ROOT / "ansible/roles/shared_data/files/registry.yaml").read_text()
    )
    apps = apps or ["paperless"]
    cold = load_module("platform/filter_plugins/cold_recovery.py")
    return {
        **connection,
        "platform_recovery_mode": True,
        "platform_recovery_apps": apps,
        "platform_recovery_operation": "recovery-test",
        "platform_bootstrap_revision": REVISION,
        "platform_recovery_token": TOKEN,
        "platform_recovery_journal": {},
        "platform_recovery_source_sha256": cold.digest(
            {"registry": registry, "revision": REVISION}
        ),
        "platform_wait_delay": 1,
        "platform_wait_retries": 1,
    }


def assert_held(state):
    consumers = {
        "paperless-main",
        "paperless-gpt",
        "paperless-gotenberg",
        "paperless-tika",
        "paperless-redis",
        "tuppr",
    }
    for event in state["events"]:
        if event["method"] not in {"POST", "PATCH"} or not isinstance(
            event.get("body"), dict
        ):
            continue
        resource = event["body"]
        kind = resource.get("kind")
        spec = resource.get("spec", {})
        if (
            kind in {"Deployment", "StatefulSet"}
            and resource["metadata"]["name"] in consumers
        ):
            assert spec.get("replicas") == 0
            assert "uid" in resource["metadata"]
        if kind == "CronJob":
            assert spec.get("suspend") is True
        if kind == "Application":
            assert not spec.get("syncPolicy", {}).get("automated")
            assert (
                resource["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"]
                == "true"
            )
        if kind == "ApplicationSet":
            assert spec["generators"] == [{"list": {"elements": []}}]
            assert not spec["template"]["spec"].get("syncPolicy", {}).get("automated")
        assert kind not in {
            "TalosUpgrade",
            "KubernetesUpgrade",
            "HTTPRoute",
            "DNSEndpoint",
        }
        if kind == "Job":
            assert (
                resource["metadata"]["name"].startswith("cold-")
                and spec["suspend"] is True
            )
        if kind == "Pod":
            assert resource["metadata"]["name"].startswith("cold-warmup-")
            assert spec["automountServiceAccountToken"] is False


@pytest.mark.parametrize("failure", ["", "mid-apply"])
def test_real_cold_role_native_render_failure_retry_held(
    tmp_path, monkeypatch, failure
):
    extend_api(monkeypatch)
    git_boundary(tmp_path)
    with api.maintenance_api(tmp_path, infrastructure_objects()) as (connection, state):
        threads, workers = start_job_workers(
            tmp_path, connection, state, failure=failure
        )
        params = {
            **variables(connection),
            "platform_recovery_image": IMAGE,
            "platform_recovery_job_timeout": 1800,
        }
        result = run_role(
            tmp_path, "platform", "recovery_dispatch", params, timeout=2100
        )
        (tmp_path / "dispatch.log").write_text(result.stdout + result.stderr)
        diagnostic = "".join(
            (p.read_text()[-12000:] for p in tmp_path.glob("worker-*/result.log"))
        )
        assert (result.returncode == 0) == (not failure), (
            result.stdout[-16000:] + result.stderr + diagnostic
        )
        assert_held(state)
        cm = state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-cold-recovery"
        ]
        journal = json.loads(cm["data"]["journal.json"])
        assert journal["phase"] == ("held" if not failure else "bootstrapping")
        assert journal["revision"] == REVISION
        assert journal["apps"] == ["paperless"]
        assert journal["executor"]["pod_uid"]
        assert journal["executor"]["image_revision"] == "f" * 40
        assert len(journal["inventory"]) > 20
        if failure:
            del state["objects"][
                "/apis/apps/v1/namespaces/platform-system/deployments/redis"
            ]
            retry = run_role(
                tmp_path, "platform", "recovery_dispatch", params, timeout=2100
            )
            (tmp_path / "retry.log").write_text(retry.stdout + retry.stderr)
            diagnostic = "".join(
                p.read_text()[-12000:] for p in tmp_path.glob("worker-*/result.log")
            )
            assert retry.returncode == 0, (
                retry.stdout[-16000:] + retry.stderr + diagnostic
            )
            assert_held(state)
        for thread in threads:
            thread.join(timeout=10)
            assert not thread.is_alive()
        resources = list(state["objects"].values())
        names = {
            r["metadata"]["name"]
            for r in resources
            if r["kind"] == "Deployment"
            and r["metadata"]["name"].startswith("paperless")
        }
        assert {
            "paperless-main",
            "paperless-gpt",
            "paperless-gotenberg",
            "paperless-tika",
            "paperless-redis",
        } == names
        assert all(
            r["spec"]["replicas"] == 0
            for r in resources
            if r["kind"] == "Deployment" and r["metadata"]["name"] in names | {"tuppr"}
        )
        assert not any(
            r["kind"] in {"TalosUpgrade", "KubernetesUpgrade"} for r in resources
        )
        assert (
            state["objects"][
                "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
            ]["spec"]["holderIdentity"]
            == ""
        )
        assert not any(
            r["kind"] in {"ClusterRole", "ClusterRoleBinding", "ServiceAccount"}
            and r["metadata"]["name"].startswith("cold-")
            for r in resources
        )


@pytest.mark.parametrize("existing", [True, False])
def test_cold_preflight_refuses_existing_consumer_before_mutation(
    tmp_path, monkeypatch, existing
):
    extend_api(monkeypatch)
    resources = []
    if existing:
        resources = [
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "paperless-main",
                    "namespace": "selfhosted",
                    "uid": "existing",
                    "resourceVersion": "1",
                },
                "spec": {"replicas": 0},
            }
        ]
    with api.maintenance_api(tmp_path, resources) as (connection, state):
        result = run_role(
            tmp_path,
            "platform",
            "recovery_preflight",
            variables(connection),
            timeout=100,
        )
        assert (result.returncode == 0) == (not existing), result.stdout + result.stderr
        assert all(e["method"] == "GET" for e in state["events"])


def test_admission_interface_rejects_flag_without_completed_restore(
    tmp_path, monkeypatch
):
    extend_api(monkeypatch)
    journal = {
        **{
            k: v
            for k, v in [
                ("version", 1),
                ("apps", ["paperless"]),
                ("revision", REVISION),
                ("token", TOKEN),
                ("phase", "held"),
            ]
        }
    }
    resources = []
    for name, value in [
        ("shared-data-cold-recovery", journal),
        ("shared-data-operation", {"confirm": True}),
    ]:
        resources.append(
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": name,
                    "namespace": "selfhosted",
                    "uid": name,
                    "resourceVersion": "1",
                },
                "data": {"journal.json": json.dumps(value)},
            }
        )
    with api.maintenance_api(tmp_path, resources) as (connection, state):
        result = run_role(tmp_path, "platform", "recovery_admission", connection)
        assert result.returncode != 0
        assert all(e["method"] == "GET" for e in state["events"])


def test_first_journal_claim_accepts_api_omitted_empty_data(tmp_path, monkeypatch):
    extend_api(monkeypatch)
    import jsonpatch

    lease_helpers = load_module("platform/filter_plugins/cold_executor.py")
    resource = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "shared-data-cold-recovery",
            "namespace": "selfhosted",
            "uid": "empty",
            "resourceVersion": "1",
        },
    }
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": "boot",
            "namespace": "platform-system",
            "uid": "job",
            "resourceVersion": "1",
        },
        "spec": {
            "suspend": True,
            "template": {
                "spec": {
                    "serviceAccountName": "boot",
                    "restartPolicy": "Never",
                    "containers": [{"name": "bootstrap", "image": IMAGE}],
                }
            },
        },
    }
    actor = {
        "kind": "Job",
        "uid": "job",
        "name": "boot",
        "namespace": "platform-system",
    }
    context = {
        "apps": ["paperless"],
        "revision": REVISION,
        "source_sha256": "c" * 64,
        "image": IMAGE,
        "code_sha256": "d" * 64,
        "bundle_sha256": "e" * 64,
    }
    lease = {
        "apiVersion": "coordination.k8s.io/v1",
        "kind": "Lease",
        "metadata": {
            "name": "shared-data-operation",
            "namespace": "selfhosted",
            "uid": "lease",
            "resourceVersion": "1",
        },
        "spec": {},
    }
    lease = jsonpatch.apply_patch(
        lease,
        lease_helpers.cold_lease_patch(lease, "", "recovery-test", actor, context, 0),
    )
    with api.maintenance_api(tmp_path, [resource, job, lease]) as (connection, state):
        params = {
            **variables(connection),
            "platform_recovery_journal": {
                "version": 1,
                "phase": "bootstrap-claimed",
                "token": TOKEN,
                "executor": {"job_uid": "job"},
            },
            "platform_recovery_context": context,
            "platform_recovery_dispatch_owner_uid": "job",
            "platform_recovery_job_actor": actor,
            "platform_recovery_journal_uid": "empty",
            "platform_recovery_journal_resource_version": "1",
            "platform_recovery_journal_first_claim": True,
            "platform_recovery_journal_empty_data": True,
        }
        result = run_role(tmp_path, "platform", "recovery_save", params)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            json.loads(
                state["objects"][api.path_for(resource)]["data"]["journal.json"]
            )["token"]
            == TOKEN
        )
