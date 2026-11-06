"""API-only health evidence; no application storage or credential access."""

from datetime import UTC, datetime


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Health timestamps must include a timezone")
    return parsed.astimezone(UTC).timestamp()


def backup_health(status, now, maximum_age=26 * 3600):
    try:
        age = float(now) - timestamp(status.get("data", {})["captured_at"])
        return 0 <= age <= maximum_age
    except KeyError, TypeError, ValueError, AttributeError:
        return False


def operation_health(journal, lease, jobs, now, watchdog_failed=False):
    if watchdog_failed:
        return False
    spec = lease.get("spec", {})
    if spec.get("holderIdentity"):
        try:
            if float(now) >= timestamp(spec["renewTime"]) + int(
                spec["leaseDurationSeconds"]
            ):
                return False
        except KeyError, TypeError, ValueError, AttributeError:
            return False
    elif journal and journal.get("phase") != "complete":
        return False
    latest = {}
    for job in jobs:
        metadata = job.get("metadata", {})
        role = metadata.get("labels", {}).get("home-ops/data-role")
        if role not in {"coordinator", "upload"}:
            owners = metadata.get("ownerReferences", [])
            if any(
                owner.get("kind") == "CronJob"
                and owner.get("name") in {"shared-data-main", "shared-data-provision"}
                for owner in owners
            ):
                role = "coordinator"
            else:
                continue
        conditions = job.get("status", {}).get("conditions", [])
        terminal = [
            condition["type"]
            for condition in conditions
            if condition.get("type") in {"Failed", "Complete"}
            and condition.get("status") == "True"
        ]
        if not terminal:
            continue
        try:
            created = timestamp(metadata["creationTimestamp"])
        except KeyError, TypeError, ValueError, AttributeError:
            return False
        if role not in latest or created >= latest[role][0]:
            latest[role] = (created, "Failed" not in terminal)
    return all(success for _, success in latest.values())


class FilterModule:
    def filters(self):
        return {
            "shared_data_backup_health": backup_health,
            "shared_data_operation_health": operation_health,
        }
