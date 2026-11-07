"""Real restore role sequencing with synthetic native command results and API."""

import json
import sys

import pytest

from tests.integration import test_data_maintenance as api
from tests.integration.cold_bootstrap.support import IMAGE, image_fixture
from tests.support.runtime import load_module, run_role

TOKEN = "c" * 32
REVISION = "a" * 40


@pytest.mark.parametrize("fail_step", ["", "provision", "postgres", "validate-final"])
def test_cold_restore_provisions_before_restore_and_preserves_zero_originals(
    tmp_path, fail_step
):
    resources, variables = api.scenario_objects()
    for resource in resources:
        kind = resource["kind"]
        if kind == "Application":
            resource["spec"]["syncPolicy"].pop("automated")
        if kind == "Deployment":
            resource["spec"]["replicas"] = 0
            if resource["metadata"]["name"] == "paperless":
                resource["spec"]["template"] = {
                    "spec": {
                        "containers": [
                            {
                                "name": "app",
                                "image": "example/paperless@sha256:" + "d" * 64,
                            }
                        ]
                    }
                }
        if kind == "CronJob":
            resource["spec"]["suspend"] = True
    registry = variables["shared_data_registry"]
    registry["consumers"]["paperless"].update(
        backend="postgresql",
        roles=[{"name": "paperless", "password_key": "paperless"}],
        databases=[{"name": "paperless", "owner": "paperless"}],
        pvcs=["selfhosted/paperless"],
    )
    image_root, image_proof = image_fixture(tmp_path)
    for resource in resources:
        if resource["kind"] == "Pod" and resource["metadata"]["name"] == "coordinator":
            resource["spec"].update(
                {"containers": [{"name": "operations", "image": IMAGE}]}
            )
    cold = load_module("platform/filter_plugins/cold_recovery.py")
    journal = {
        "version": 1,
        "phase": "held",
        "token": TOKEN,
        "revision": REVISION,
        "apps": ["paperless"],
        "inventory": cold.cold_inventory([r for r in resources if r["kind"] != "Pod"]),
    }
    journal["executor"] = {
        "code_sha256": image_proof["code_sha256"],
        "job_uid": "bootstrap-job",
        "pod_uid": "bootstrap-pod",
        "image": IMAGE,
        "image_revision": image_proof["image_revision"],
    }
    journal["source_sha256"] = cold.digest({"registry": registry, "revision": REVISION})
    resources.append(
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "shared-data-cold-recovery",
                "namespace": "selfhosted",
                "uid": "cold-uid",
                "resourceVersion": "1",
            },
            "data": {"journal.json": json.dumps(journal)},
        }
    )
    wrapper = tmp_path / "native-fixture"
    actions = tmp_path / "actions.json"
    wrapper.write_text(
        "#!"
        + sys.executable
        + "\n"
        + f"""
import json,sys
from pathlib import Path
path=Path({str(actions)!r})
rows=json.loads(path.read_text()) if path.exists() else []
step=sys.argv[2]
rows.append(step)
path.write_text(json.dumps(rows))
failed={fail_step!r}
if step==failed or (failed=='validate-final' and step=='validate' and rows.count('validate')==2):raise SystemExit(1)
print(json.dumps({{'snapshot':'e'*64,'selection_sha256':'b'*64,'manifest_sha256':'c'*64,'apps':['paperless'],'root':'/synthetic/stage'}}))
"""
    )
    wrapper.chmod(0o700)
    variables.update(
        shared_data_action="restore",
        shared_data_operation_id="cold-restore",
        shared_data_operation_kind="restore",
        shared_data_recovery_mode=True,
        shared_data_image=IMAGE,
        shared_data_cold_image_root=str(image_root),
        shared_data_python=str(wrapper),
        shared_data_staging=str(tmp_path / "stage"),
        shared_data_recovery_budget=120,
        shared_data_lease_duration=900,
    )
    with api.maintenance_api(tmp_path, resources) as (connection, state):
        result = run_role(
            tmp_path, "shared_data", "main", {**connection, **variables}, timeout=600
        )
        assert (result.returncode == 0) == (not fail_step), (
            result.stdout[-16000:] + result.stderr
        )
        receipt = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        actions = json.loads(actions.read_text())
        assert (
            actions.index("provision") < actions.index("postgres")
            if "postgres" in actions
            else True
        )
        for resource in state["objects"].values():
            if resource["kind"] == "Deployment":
                assert resource["spec"]["replicas"] == 0
            if resource["kind"] == "Application":
                assert not resource["spec"].get("syncPolicy", {}).get("automated")
            if resource["kind"] == "CronJob":
                assert resource["spec"]["suspend"] is True
        if fail_step:
            assert receipt["phase"] != "complete"
            with pytest.raises(ValueError):
                cold.cold_admission(journal, receipt, registry)
        else:
            assert receipt["phase"] == "complete"
            assert receipt["cold_token"] == TOKEN
            assert actions == [
                "stage",
                "quiet",
                "provision",
                "redis-provision",
                "validate",
                "postgres",
                "files",
                "validate",
            ]
            capability = cold.cold_admission(journal, receipt, registry)
            assert capability["apps"] == ["paperless"]
