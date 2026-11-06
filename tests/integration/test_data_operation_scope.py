"""Native operation scope errors fail before any Kubernetes API request."""

from copy import deepcopy

import pytest

from tests.integration import test_data_maintenance as api
from tests.support.data_generation import operations_image
from tests.support.runtime import run_role


@pytest.mark.parametrize("action", ["backup", "provision"])
@pytest.mark.parametrize("apps", [["karakeep"], ["paperless", "karakeep"]])
@pytest.mark.parametrize(
    "entry,invocation,confirm",
    [
        ("main", "action", False),
        ("main", "plan", False),
        ("main", "submit", False),
        ("main", "submit", True),
        ("main", "action", True),
        ("direct", "action", True),
        ("submit", "submit", True),
    ],
)
def test_native_operation_rejects_file_scope_before_api(
    tmp_path, action, apps, entry, invocation, confirm
):
    objects, variables = api.scenario_objects()
    registry = variables["shared_data_registry"]
    registry["file_consumers"] = {
        "karakeep": deepcopy(registry["consumers"]["paperless"])
    }
    variables.update(
        shared_data_apps=apps,
        shared_data_action=action if invocation == "action" else invocation,
        shared_data_job_action=action,
        shared_data_operation_kind=action,
        shared_data_confirm=confirm,
        shared_data_image=operations_image(native=False),
        shared_data_job_timeout=5,
        shared_data_root=str(tmp_path / "appdata"),
        shared_data_staging=str(tmp_path / "staging"),
        shared_data_credentials=str(tmp_path / "credentials"),
        # A self-contained coordinator must reject scope before registry API reads.
        shared_data_require_current_registry=True,
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        state["job_created"] = lambda job, _: job.update(status={"succeeded": 1})
        result = run_role(
            tmp_path,
            "shared_data",
            action if entry == "direct" else entry,
            {**connection, **variables},
            env={"KUBECONFIG": connection["kubeconfig_path"]},
        )
        output = result.stdout + result.stderr
        assert state["events"] == [], output
        assert result.returncode != 0, output
        assert "registered native consumers" in output, output


@pytest.mark.parametrize("action", ["backup", "provision"])
@pytest.mark.parametrize("invocation", ["action", "plan", "submit"])
def test_native_preview_accepts_pre_onboarding_sqlite(tmp_path, action, invocation):
    objects, variables = api.scenario_objects()
    variables["shared_data_registry"]["consumers"]["paperless"].update(
        enabled=False, backend="sqlite"
    )
    variables.update(
        shared_data_action=action if invocation == "action" else invocation,
        shared_data_job_action=action,
        shared_data_confirm=False,
        shared_data_image=operations_image(native=False),
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, "shared_data", "main", {**connection, **variables})
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["events"] == []


@pytest.mark.parametrize("action", ["restore", "cleanup"])
def test_combined_scope_remains_valid_for_recovery_and_cleanup(tmp_path, action):
    objects, variables = api.scenario_objects()
    registry = variables["shared_data_registry"]
    registry["file_consumers"] = {
        "karakeep": deepcopy(registry["consumers"]["paperless"])
    }
    variables.update(
        shared_data_apps=["paperless", "karakeep"],
        shared_data_action="submit",
        shared_data_job_action=action,
        shared_data_confirm=False,
        shared_data_image=operations_image(native=False),
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(tmp_path, "shared_data", "main", {**connection, **variables})
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["events"] == []


@pytest.mark.parametrize("action", ["backup", "provision"])
@pytest.mark.parametrize("entry", ["main", "direct"])
@pytest.mark.parametrize("apps", [["unregistered"], ["paperless", "paperless"]])
def test_native_scope_still_rejects_unregistered_and_duplicate_apps(
    tmp_path, action, entry, apps
):
    objects, variables = api.scenario_objects()
    variables.update(
        shared_data_apps=apps,
        shared_data_action=action,
        shared_data_operation_kind=action,
        shared_data_image=operations_image(native=False),
    )
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            action if entry == "direct" else entry,
            {**connection, **variables},
        )
        assert state["events"] == [], result.stdout + result.stderr
        assert result.returncode != 0
        assert "unique registered application names" in result.stdout + result.stderr
