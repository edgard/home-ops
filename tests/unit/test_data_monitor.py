"""Health derives from verified capture time and durable operation evidence."""

from tests.support.runtime import load_module


def monitor():
    return load_module("shared_data/filter_plugins/monitor.py")


def job(role, at, failed=False):
    return {
        "metadata": {"creationTimestamp": at, "labels": {"home-ops/data-role": role}},
        "status": {
            "conditions": [
                {"type": "Failed" if failed else "Complete", "status": "True"}
            ]
        },
    }


def test_backup_health_uses_capture_age_never_operation_or_upload_time():
    data = monitor()
    now = 1793898000
    assert data.backup_health({}, now) is False
    assert data.backup_health({"data": {"captured_at": "invalid"}}, now) is False
    assert (
        data.backup_health({"data": {"captured_at": "2026-11-05T18:20:00Z"}}, now)
        is False
    )
    assert (
        data.backup_health({"data": {"captured_at": "2026-11-04T17:00:00Z"}}, now)
        is True
    )
    assert (
        data.backup_health({"data": {"captured_at": "2026-11-04T10:00:00Z"}}, now)
        is False
    )


def test_failed_upload_stays_unhealthy_until_new_upload_success():
    data = monitor()
    jobs = [
        job("upload", "2026-11-05T10:00:00Z", True),
        job("coordinator", "2026-11-05T11:00:00Z"),
    ]
    assert data.operation_health({}, {}, jobs, 1793898000) is False
    jobs.append(job("upload", "2026-11-05T12:00:00Z"))
    assert data.operation_health({}, {}, jobs, 1793898000) is True


def test_incomplete_or_expired_operation_and_watchdog_failure_are_unhealthy():
    data = monitor()
    journal = {"phase": "held"}
    lease = {
        "spec": {
            "holderIdentity": "op:uid",
            "renewTime": "2026-11-05T15:39:00Z",
            "leaseDurationSeconds": 900,
        }
    }
    now = 1793893200  # 15:40 UTC
    assert data.operation_health(journal, lease, [], now) is True
    assert data.operation_health(journal, lease, [], now + 901) is False
    assert data.operation_health(journal, {}, [], now) is False
    assert data.operation_health({}, {}, [], now, watchdog_failed=True) is False
