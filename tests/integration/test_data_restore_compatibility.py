"""Existing confirmed Restic commands reach database-aware shared recovery."""

import json

import pytest

from tests.support.runtime import PLAYBOOK, ROOT, environment, run_command


@pytest.mark.parametrize("mode,app", [("app", "paperless"), ("all", "")])
def test_existing_restore_playbook_previews_combined_recovery_without_api(
    tmp_path, mode, app
):
    result = run_command(
        [
            str(PLAYBOOK),
            str(ROOT / "ansible/playbooks/restic-restore.yml"),
            "--extra-vars",
            json.dumps(
                {
                    "restic_restore_mode": mode,
                    "restic_restore_app": app,
                    "restic_restore_snapshot": "selected-snapshot",
                    "restic_restore_confirm": False,
                }
            ),
        ],
        env=environment(tmp_path),
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"action": "restore"' in result.stdout
    assert '"snapshot": "selected-snapshot"' in result.stdout
    assert '"backend": "sqlite"' in result.stdout
    assert "changed=0" in result.stdout
