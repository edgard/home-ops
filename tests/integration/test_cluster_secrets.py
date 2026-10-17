import base64
import json

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import run_role

TOKEN = "synthetic-read-only-token"
OLD = base64.b64encode(b"synthetic-previous-token").decode()
NEW = base64.b64encode(TOKEN.encode()).decode()


@pytest.mark.parametrize(
    "scenario,patches",
    [
        ("success", [NEW]),
        ("ambiguous-patch", [NEW, OLD]),
        ("reconciliation-failure", [NEW, OLD]),
        ("missing-previous-token", []),
        ("malformed-previous-token", []),
        ("previous-read-failure", []),
        ("store-read-failure", [NEW, OLD]),
        ("es-read-failure", [NEW, OLD]),
        ("target-read-failure", [NEW, OLD]),
        ("restore-failure", [NEW, OLD]),
        ("invalid-provider-access", []),
    ],
)
def test_token_rotation_and_rollback(tmp_path, provider, secret_api, scenario, patches):
    projects, _, targets, manifests = provider
    if scenario == "invalid-provider-access":
        (tmp_path / "projects.json").write_text(json.dumps(projects[:-1]))
    with cluster_api(
        tmp_path,
        {
            **secret_api,
            "scenario": scenario,
            "token": OLD,
            "patches": [],
            "reads": [],
            "target_keys": targets,
        },
    ) as (connection, observed):
        result = run_role(
            tmp_path,
            "platform",
            "sync_token",
            {
                **connection,
                "platform_bitwarden_access_token": TOKEN,
                "platform_secret_reconcile_timeout": (
                    120 if scenario == "success" else 3
                ),
            },
        )
        state = observed()
    output = result.stdout + result.stderr
    assert (result.returncode == 0) == (scenario == "success"), output
    assert state["patches"] == patches, output
    assert state["patch_paths"] == [secret_api["credential_path"]] * len(patches)
    assert state["token"] == (NEW if scenario == "success" else OLD)
    assert "SYNTHETIC-PRIVATE" not in output
    assert TOKEN not in output and "synthetic-previous-token" not in output
    if scenario == "invalid-provider-access":
        assert not state["reads"]
    boundaries = {
        "previous-read-failure": "/api/v1/namespaces/platform-system/secrets/bitwarden-credentials",
        "store-read-failure": "/apis/external-secrets.io/v1/clustersecretstores/external-secrets-store",
        "es-read-failure": f"/apis/external-secrets.io/v1/namespaces/{manifests[0]['metadata']['namespace']}/externalsecrets/{manifests[0]['metadata']['name']}",
        "target-read-failure": f"/api/v1/namespaces/{manifests[0]['metadata']['namespace']}/secrets/{manifests[0]['spec']['target']['name']}",
    }
    if scenario in boundaries:
        assert boundaries[scenario] in state["reads"], output
    if len(patches) == 2:
        assert (
            "previous token restoration failed"
            if scenario == "restore-failure"
            else "previous token restored"
        ) in output


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "extra-project",
        "missing-project",
        "malformed-projects",
        "invalid-project-json",
        "invalid-secret-json",
        "malformed-secret-shape",
        "duplicate-keys",
        "missing-application-key",
        "missing-repo-credential",
    ],
)
def test_provider_access(tmp_path, provider, scenario):
    projects, values, _, _ = provider
    changes = {
        "extra-project": ("projects", projects + [{"id": "extra-project"}]),
        "missing-project": ("projects", projects[:-1]),
        "malformed-projects": ("projects", {}),
        "invalid-project-json": ("projects", None),
        "invalid-secret-json": ("secrets", None),
        "malformed-secret-shape": ("secrets", {}),
        "duplicate-keys": ("secrets", values + values[:1]),
        "missing-application-key": ("secrets", values[1:]),
        "missing-repo-credential": (
            "secrets",
            [v for v in values if v["key"] != "argocd_repo_password"],
        ),
    }
    if scenario in changes:
        name, value = changes[scenario]
        (tmp_path / (name + ".json")).write_text(
            "SYNTHETIC-PRIVATE-PROVIDER-DIAGNOSTIC"
            if value is None
            else json.dumps(value)
        )
    result = run_role(
        tmp_path,
        "platform",
        "application_access",
        {"platform_bitwarden_access_token": TOKEN},
    )
    output = result.stdout + result.stderr
    assert (result.returncode == 0) == (scenario == "success"), output
    assert "SYNTHETIC-PRIVATE" not in output and TOKEN not in output
    if scenario != "success":
        assert "Application credential validation failed" in output


@pytest.mark.parametrize(
    "scenario", ["handoff-success", "root-advanced", "appset-recreated"]
)
def test_committed_handoff(tmp_path, provider, secret_api, scenario):
    _, _, targets, manifests = provider
    with cluster_api(
        tmp_path,
        {
            **secret_api,
            "scenario": scenario,
            "token": OLD,
            "patches": [],
            "reads": [],
            "target_keys": targets,
            "applications": ["fixture-owned"],
        },
    ) as (connection, observed):
        result = run_role(
            tmp_path,
            "platform",
            "handoff",
            {
                **connection,
                "platform_bootstrap_revision": "synthetic-merged-head",
                "platform_handoff_timeout": 120,
                "platform_expected_applications": ["fixture-owned"],
                "platform_secret_reconcile_timeout": 120,
                "platform_secret_manifests": manifests[:1],
            },
        )
        state = observed()
    assert (result.returncode == 0) == (scenario == "handoff-success"), (
        result.stdout + result.stderr
    )
    assert state["root_reads"] > 1 and state["appset_reads"] > 1
    assert not state["patches"]
