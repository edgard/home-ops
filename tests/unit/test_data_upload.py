import json
import sys
from unittest.mock import patch

import pytest

from tests.support.runtime import load_module


def module():
    with patch.dict(
        sys.modules, {"data_tools": load_module("shared_data/files/data_tools.py")}
    ):
        return load_module("shared_data/files/upload.py")


def test_failed_or_partial_backup_never_tags_success():
    calls = []

    def run(command):
        calls.append(command)
        return 3, json.dumps({"message_type": "summary", "snapshot_id": "incomplete"})

    with pytest.raises(ValueError):
        module().upload("op", {"version": 1}, run)
    assert not any("tag" in c for c in calls)


def test_promotion_requires_matching_stored_manifest():
    calls = []

    def run(command):
        calls.append(command)
        if "backup" in command:
            return 0, json.dumps({"message_type": "summary", "snapshot_id": "pending"})
        if "dump" in command:
            return 0, json.dumps({"version": 1, "operation": "wrong"})
        raise AssertionError("must not promote")

    with pytest.raises(ValueError, match="manifest"):
        module().upload("op", {"version": 1, "operation": "op"}, run)
    assert not any("tag" in c for c in calls)


def test_success_promotes_only_this_pending_snapshot():
    calls = []
    manifest = {"version": 1, "operation": "op"}

    def run(command):
        calls.append(command)
        if "backup" in command:
            return 0, json.dumps({"message_type": "summary", "snapshot_id": "pending"})
        if "dump" in command:
            return 0, json.dumps(manifest)
        if "tag" in command:
            return 0, ""
        if "snapshots" in command:
            if command[-1] == "pending":
                return 0, json.dumps([{"id": "pending", "tree": "tree"}])
            return 0, json.dumps(
                [
                    {
                        "id": "final",
                        "original": "pending",
                        "tags": ["appdata"],
                        "tree": "tree",
                    },
                    {
                        "id": "older-identical",
                        "original": "other",
                        "tags": ["appdata"],
                        "tree": "tree",
                    },
                ]
            )
        raise AssertionError(command)

    result = module().upload("op", manifest, run)
    assert result == "final"
    tag = next(c for c in calls if "tag" in c)
    assert tag[-1] == "pending" and "appdata-pending" in tag
