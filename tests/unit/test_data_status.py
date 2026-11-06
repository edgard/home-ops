"""A delayed successful retry cannot make old data look newly recoverable."""

from tests.support.runtime import load_module


def test_capture_status_never_replaces_newer_success_with_older_retry():
    data = load_module("shared_data/filter_plugins/data.py")
    current = {"data": {"captured_at": "2026-11-05T01:00:00Z", "snapshot": "a" * 64}}
    older = {"captured_at": "2026-11-04T01:00:00+00:00", "snapshot": "b" * 64}
    assert data.newer_capture(current, older) is False
    assert data.newer_capture({}, older) is True
    newer = {"captured_at": "2026-11-05T03:30:00+02:00", "snapshot": "c" * 64}
    assert data.newer_capture(current, newer) is True
