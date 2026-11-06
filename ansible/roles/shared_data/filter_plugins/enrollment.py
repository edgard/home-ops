"""Narrow nonsecret enrollment plans. All Kubernetes I/O stays in Ansible."""

import hashlib
import json
from copy import deepcopy

ENV = {"PAPERLESS_WORKER_TIMEOUT": "1800", "S6_KILL_GRACETIME": "3000"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def app_container(template):
    matches = [row for row in template["spec"]["containers"] if row["name"] == "app"]
    if len(matches) != 1:
        raise ValueError("exactly one app container required")
    return matches[0]


def stripped(template):
    value = deepcopy(template)
    value["spec"].pop("terminationGracePeriodSeconds", None)
    app = app_container(value)
    app.pop("livenessProbe", None)
    app["image"] = app["image"].split("@", 1)[0]
    app["env"] = sorted(
        [row for row in app.get("env", []) if row["name"] not in ENV],
        key=lambda row: row["name"],
    )
    return value


def shared_data_enrollment_delta(original, desired):
    if stripped(original) != stripped(desired):
        raise ValueError("enrollment permits a shutdown-only template change")
    return {"original_sha256": digest(original), "desired_sha256": digest(desired)}


def shared_data_enrollment_overlay(current, rendered):
    """Apply only approved shutdown settings, preserving all admission/live fields."""
    result = deepcopy(current)
    src = app_container(rendered)
    dest = app_container(result)
    if dest["image"].split("@", 1)[0] != src["image"].split("@", 1)[0]:
        raise ValueError("shutdown-only enrollment cannot change image version")
    result["spec"]["terminationGracePeriodSeconds"] = rendered["spec"][
        "terminationGracePeriodSeconds"
    ]
    dest["image"] = src["image"]
    dest["livenessProbe"] = deepcopy(src["livenessProbe"])
    dest["env"] = [row for row in dest.get("env", []) if row["name"] not in ENV] + [
        row for row in src.get("env", []) if row["name"] in ENV
    ]
    shared_data_enrollment_delta(current, result)
    return result


def shared_data_enrollment_patch(current, uid, desired):
    if current["metadata"]["uid"] != uid:
        raise ValueError("enrollment controller identity changed")
    if current["spec"].get("replicas", 1) != 0:
        raise ValueError("enrollment requires zero replicas")
    shared_data_enrollment_delta(current["spec"]["template"], desired)
    return [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": current["metadata"]["resourceVersion"],
        },
        {"op": "test", "path": "/spec/replicas", "value": 0},
        {"op": "add", "path": "/spec/template", "value": desired},
    ]


def shared_data_enrollment_service_patch(current, snapshot, operation, restore=False):
    if current["metadata"]["uid"] != snapshot["uid"]:
        raise ValueError("enrollment Service identity changed")
    fence = {"home-ops/enrollment-fence": operation}
    if current["spec"].get("selector") not in [snapshot["selector"], fence]:
        raise ValueError("enrollment Service selector changed")
    return [
        {"op": "test", "path": "/metadata/uid", "value": snapshot["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": current["metadata"]["resourceVersion"],
        },
        {
            "op": "add",
            "path": "/spec/selector",
            "value": snapshot["selector"] if restore else fence,
        },
    ]


def shared_data_enrollment_services(resources, labels):
    return sorted(
        [
            row
            for row in resources
            if row.get("spec", {}).get("selector")
            and all(
                labels.get(key) == value
                for key, value in row["spec"]["selector"].items()
            )
        ],
        key=lambda row: row["metadata"]["name"],
    )


def shared_data_enrollment_settings(template):
    app = app_container(template)
    return {
        "grace": template["spec"].get("terminationGracePeriodSeconds", 30),
        "image": app["image"],
        "livenessProbe": app.get("livenessProbe"),
        "env": [row for row in app.get("env", []) if row["name"] in ENV],
    }


def shared_data_enrollment_protected(template, protocol):
    app = app_container(template)
    env = {row["name"]: row.get("value") for row in app.get("env", [])}
    if (
        template["spec"].get("terminationGracePeriodSeconds", 30)
        < protocol["minimum_grace_seconds"]
        or app["image"] != protocol["image"]
        or any(env.get(key) != value for key, value in protocol["required_env"].items())
        or app.get("livenessProbe", {}).get("exec", {}).get("command")
        != protocol["required_liveness_command"]
    ):
        raise ValueError(
            "actual template lacks rehearsed Paperless shutdown protection"
        )
    return True


class FilterModule:
    def filters(self):
        return {
            "shared_data_enrollment_protected": shared_data_enrollment_protected,
            "shared_data_enrollment_services": shared_data_enrollment_services,
            "shared_data_enrollment_settings": shared_data_enrollment_settings,
            "shared_data_enrollment_delta": shared_data_enrollment_delta,
            "shared_data_enrollment_overlay": shared_data_enrollment_overlay,
            "shared_data_enrollment_patch": shared_data_enrollment_patch,
            "shared_data_enrollment_service_patch": shared_data_enrollment_service_patch,
            "shared_data_enrollment_digest": digest,
        }
