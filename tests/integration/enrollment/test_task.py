"""The public operator Task previews its exact session without contacting Kubernetes."""

import json

import pytest

from tests.support.runtime import ROOT, environment, run_command

from .api import maintenance_api


@pytest.mark.parametrize("file_confirm", [False, True])
def test_operator_task_requires_explicit_confirmation_outside_settings(
    tmp_path, file_confirm
):
    settings = tmp_path / "session settings.json"
    with maintenance_api(tmp_path, []) as (connection, state):
        settings.write_text(
            json.dumps(
                {
                    **connection,
                    "shared_data_confirm": file_confirm,
                    "shared_data_operator_step": "enroll",
                    "shared_data_operation_id": "preview-enrollment",
                    "shared_data_apps": ["paperless"],
                    "shared_data_holder_pod_name": "exact-actor",
                    "shared_data_holder_pod_uid": "exact-uid",
                    "shared_data_source_revision": "a" * 40,
                }
            )
        )
        result = run_command(
            ["task", "data:operator", f"settings={settings}"],
            cwd=ROOT,
            env=environment(tmp_path),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for value in (
            "enroll",
            "preview-enrollment",
            "exact-actor",
            "exact-uid",
            "a" * 40,
        ):
            assert value in result.stdout
        assert "confirmation_required" in result.stdout
        assert not state["events"]
