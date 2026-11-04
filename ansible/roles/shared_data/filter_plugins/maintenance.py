"""Pure maintenance plans. Kubernetes I/O belongs exclusively to role tasks.

The journal deliberately contains no consumer credentials or rendered pod specs.
JSON patches compare object identity and resourceVersion before every mutation.
"""

import json
import re
from copy import deepcopy
from datetime import datetime, timezone

_OPERATION = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_KINDS = {"backup", "restore", "migration", "rotation", "provision"}
_LABEL = "home-ops/data-operation"


def shared_data_targets(
    registry,
    apps,
    operation_id,
    operation_kind,
    tuppr_namespace="platform-system",
    tuppr_name="tuppr",
):
    if not isinstance(operation_id, str) or not _OPERATION.fullmatch(operation_id):
        raise ValueError("operation ID must be a restricted nonempty DNS name")
    if operation_kind not in _KINDS:
        raise ValueError("unsupported maintenance operation kind")
    if registry.get("version") != 1 or not isinstance(registry.get("consumers"), dict):
        raise ValueError("registry version 1 and consumers mapping are required")
    if not isinstance(apps, list) or not apps or len(set(apps)) != len(apps):
        raise ValueError("select a nonempty unique list of registered consumers")
    targets = [
        {
            "api_version": "argoproj.io/v1alpha1",
            "kind": "Application",
            "namespace": "argocd",
            "name": "root",
            "role": "root",
        },
        {
            "api_version": "argoproj.io/v1alpha1",
            "kind": "ApplicationSet",
            "namespace": "argocd",
            "name": "apps",
            "role": "appset",
        },
    ]
    for app in dict.fromkeys([*apps, "tuppr"]):
        if app != "tuppr" and app not in registry["consumers"]:
            raise ValueError("unknown selected consumer")
        targets.append(
            {
                "api_version": "argoproj.io/v1alpha1",
                "kind": "Application",
                "namespace": "argocd",
                "name": app,
                "role": "application",
            }
        )
    targets.append(
        {
            "api_version": "apps/v1",
            "kind": "Deployment",
            "namespace": tuppr_namespace,
            "name": tuppr_name,
            "role": "tuppr",
        }
    )
    for app in apps:
        consumer = registry["consumers"].get(app)
        if not isinstance(consumer, dict):
            raise ValueError("unknown selected consumer")
        for section, role in [("cronjobs", "cronjob"), ("workloads", "workload")]:
            for item in consumer.get(section, []):
                kind = "CronJob" if role == "cronjob" else item["kind"]
                if kind not in {"CronJob", "Deployment", "StatefulSet"}:
                    raise ValueError("unsupported writer workload kind")
                namespace = item.get("namespace", consumer["namespace"])
                if not item.get("name") or not namespace:
                    raise ValueError("writer name and namespace are required")
                targets.append(
                    {
                        "api_version": "batch/v1" if role == "cronjob" else "apps/v1",
                        "kind": kind,
                        "namespace": namespace,
                        "name": item["name"],
                        "role": role,
                    }
                )
    identities = [(row["kind"], row["namespace"], row["name"]) for row in targets]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate maintenance target")
    return targets


def shared_data_snapshot(target, resource):
    metadata = resource["metadata"]
    if not metadata.get("uid"):
        raise ValueError("target has no immutable identity")
    role = target["role"]
    field = (
        "syncPolicy"
        if role in {"root", "application", "appset"}
        else "suspend"
        if role == "cronjob"
        else "replicas"
    )
    spec = resource.get("spec", {})
    result = {
        "api_version": resource["apiVersion"],
        "kind": resource["kind"],
        "name": metadata["name"],
        "namespace": metadata["namespace"],
        "uid": metadata["uid"],
        "role": role,
        "field": field,
        "present": field in spec,
        "value": deepcopy(spec.get(field)),
    }
    if role in {"workload", "tuppr"}:
        result["selector"] = deepcopy(spec.get("selector", {}))
        if not result["selector"]:
            raise ValueError("writer has no pod selector")
    return result


def shared_data_snapshot_restored(snapshot, current):
    if current.get("metadata", {}).get("uid") != snapshot["uid"]:
        return False
    spec = current.get("spec", {})
    field = snapshot["field"]
    return (field in spec) == snapshot["present"] and (
        not snapshot["present"] or spec[field] == snapshot["value"]
    )


def shared_data_patch(snapshot, current, restore=False):
    if current["metadata"].get("uid") != snapshot["uid"]:
        raise ValueError("maintenance target identity changed; inspect before resuming")
    metadata = current["metadata"]
    patch = [{"op": "test", "path": "/metadata/uid", "value": snapshot["uid"]}]
    if "resourceVersion" in metadata:
        patch.append(
            {
                "op": "test",
                "path": "/metadata/resourceVersion",
                "value": metadata["resourceVersion"],
            }
        )
    field = snapshot["field"]
    spec = current.get("spec", {})
    path = "/spec/" + field
    if restore:
        if snapshot["present"]:
            patch.append(
                {"op": "add", "path": path, "value": deepcopy(snapshot["value"])}
            )
        elif field in spec:
            patch.append({"op": "remove", "path": path})
    else:
        role = snapshot["role"]
        value = deepcopy(snapshot["value"] or {}) if field == "syncPolicy" else None
        if role in {"root", "application"}:
            value.pop("automated", None)
        elif role == "appset":
            value["applicationsSync"] = "create-only"
        else:
            value = role == "cronjob" if role == "cronjob" else 0
        patch.append({"op": "add", "path": path, "value": value})
    return patch


def _timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def shared_data_now(_unused=None):
    return datetime.now(timezone.utc).timestamp()


def shared_data_lease_claim(
    lease, operation_id, holder_uid, now, duration=900, allow_empty=True
):
    holder = operation_id + ":" + holder_uid
    if not holder_uid or len(holder) > 128:
        raise ValueError("a valid coordinator Pod UID is required")
    spec = lease.get("spec", {})
    allowed = {holder} | ({None, ""} if allow_empty else set())
    if spec.get("holderIdentity") not in allowed:
        raise ValueError("maintenance Lease is owned by another coordinator")
    stamp = (
        datetime.fromtimestamp(float(now), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    patch = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": lease["metadata"]["resourceVersion"],
        },
    ]
    if "spec" in lease:
        patch.append({"op": "test", "path": "/spec", "value": deepcopy(spec)})
    patch.append(
        {
            "op": "add",
            "path": "/spec",
            "value": {
                **deepcopy(spec),
                "holderIdentity": holder,
                "leaseDurationSeconds": int(duration),
                "acquireTime": spec.get("acquireTime", stamp),
                "renewTime": stamp,
            },
        }
    )
    return patch


_LEASE_RECORD = "home-ops/data-coordinator"


def shared_data_lease_record(lease):
    try:
        record = json.loads(
            lease.get("metadata", {}).get("annotations", {}).get(_LEASE_RECORD, "{}")
        )
        actor = record["actor"]
        if not all(actor.get(key) for key in ("uid", "name", "namespace")):
            return {}
        if (
            lease.get("spec", {}).get("holderIdentity")
            != record["operation_id"] + ":" + actor["uid"]
        ):
            return {}
        if record["operation_kind"] not in _KINDS or record["stage"] not in {
            "claimed",
            "journaled",
        }:
            return {}
        return record
    except KeyError, TypeError, ValueError:
        return {}


def shared_data_lease_expired(lease, now):
    spec = lease.get("spec", {})
    try:
        return float(now) > _timestamp(spec["renewTime"]) + int(
            spec["leaseDurationSeconds"]
        )
    except KeyError, TypeError, ValueError:
        return False


def shared_data_lease_takeover(
    lease,
    expected_identity,
    operation_id,
    operation_kind,
    actor,
    now,
    duration=900,
    stage="journaled",
):
    """CAS ownership plus recovery identity atomically, before journal/targets."""
    spec = lease.get("spec", {})
    if spec.get("holderIdentity", "") != expected_identity:
        raise ValueError("Lease ownership changed before acquisition or recovery")
    if not all(actor.get(key) for key in ("uid", "name", "namespace")):
        raise ValueError("live executor identity is required")
    identity = operation_id + ":" + actor["uid"]
    if (
        len(identity) > 128
        or not _OPERATION.fullmatch(operation_id)
        or operation_kind not in _KINDS
    ):
        raise ValueError("invalid maintenance ownership identity")
    stamp = (
        datetime.fromtimestamp(float(now), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    changed = identity != expected_identity
    claimed = {
        **deepcopy(spec),
        "holderIdentity": identity,
        "leaseDurationSeconds": int(duration),
        "renewTime": stamp,
        "acquireTime": stamp if changed else spec.get("acquireTime", stamp),
        "leaseTransitions": int(spec.get("leaseTransitions", 0)) + int(changed),
    }
    annotations = deepcopy(lease.get("metadata", {}).get("annotations", {}))
    annotations[_LEASE_RECORD] = json.dumps(
        {
            "operation_id": operation_id,
            "operation_kind": operation_kind,
            "actor": deepcopy(actor),
            "stage": stage,
        },
        sort_keys=True,
    )
    patch = [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": lease["metadata"]["resourceVersion"],
        }
    ]
    if "spec" in lease:
        patch.append({"op": "test", "path": "/spec", "value": deepcopy(spec)})
    patch.extend(
        [
            {"op": "add", "path": "/spec", "value": claimed},
            {"op": "add", "path": "/metadata/annotations", "value": annotations},
        ]
    )
    return patch


def shared_data_lease_release(lease, expected_identity, result="completed"):
    spec = lease.get("spec", {})
    if not expected_identity or spec.get("holderIdentity") != expected_identity:
        raise ValueError("Lease ownership changed before release")
    annotations = deepcopy(lease.get("metadata", {}).get("annotations", {}))
    annotations["home-ops/data-recovery-result"] = result
    return [
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": lease["metadata"]["resourceVersion"],
        },
        {"op": "test", "path": "/spec", "value": deepcopy(spec)},
        {
            "op": "add",
            "path": "/spec",
            "value": {**deepcopy(spec), "holderIdentity": ""},
        },
        {"op": "add", "path": "/metadata/annotations", "value": annotations},
    ]


def shared_data_orphan_releasable(lease, pods, jobs, now, executor_uid=""):
    record = shared_data_lease_record(lease)
    if (
        not record
        or record["stage"] != "claimed"
        or not shared_data_lease_expired(lease, now)
    ):
        return False
    return shared_data_coordinator_fenced(
        {"operation_id": record["operation_id"], "holder": record["actor"]},
        pods,
        jobs,
        executor_uid,
    )


def _effective_coordinator(journal, lease):
    record = shared_data_lease_record(lease)
    if record:
        if (
            record["operation_id"] == journal["operation_id"]
            and record["operation_kind"] == journal["operation_kind"]
        ):
            return record["actor"]
        return None
    # Legacy journals predate the atomic identity annotation.
    actor = journal.get("coordinator", journal["holder"])
    if (
        lease.get("spec", {}).get("holderIdentity")
        == journal["operation_id"] + ":" + actor["uid"]
    ):
        return actor
    return None


def shared_data_completed_releasable(
    journal, lease, pods, jobs, now, inspected=False, executor_uid=""
):
    actor = _effective_coordinator(journal, lease)
    if journal.get("phase") != "complete" or not actor:
        return False
    if not inspected and not shared_data_lease_expired(lease, now):
        return False
    return shared_data_coordinator_fenced(
        {**journal, "lease_coordinator": actor}, pods, jobs, executor_uid
    )


def _terminal(pod):
    # Terminating is not terminated, including NFS-hung pods.
    return pod.get("status", {}).get("phase") in {"Succeeded", "Failed"}


def _job_complete(job):
    return any(
        row.get("type") in {"Complete", "Failed"} and row.get("status") == "True"
        for row in job.get("status", {}).get("conditions", [])
    )


def shared_data_recovery_fenced(journal, lease, pods, jobs, executor_uid=""):
    coordinator = _effective_coordinator(journal, lease)
    return bool(coordinator) and shared_data_coordinator_fenced(
        {**journal, "lease_coordinator": coordinator}, pods, jobs, executor_uid
    )


def shared_data_recovery(journal, lease, pods, jobs, now, executor_uid=""):
    result = {
        "resume": False,
        "record": False,
        "reason": "operator inspection required",
    }
    coordinator = _effective_coordinator(journal, lease)
    if not coordinator:
        return {**result, "reason": "Lease and journal ownership conflict"}
    if not shared_data_lease_expired(lease, now):
        return {**result, "reason": "Lease has not expired"}
    if not shared_data_coordinator_fenced(
        {**journal, "lease_coordinator": coordinator}, pods, jobs, executor_uid
    ):
        return {
            **result,
            "reason": "old coordinator or child Jobs/Pods can still write; fence them first",
        }
    if journal.get("operation_kind") != "backup":
        return {**result, "record": True}
    return {
        "resume": True,
        "record": True,
        "reason": "expired backup coordinator and children confirmed fenced",
    }


def shared_data_coordinator_fenced(journal, pods, jobs, executor_uid=""):
    actors = [journal["holder"]] + [
        journal[key] for key in ("coordinator", "lease_coordinator") if journal.get(key)
    ]
    actor_uids = {row["uid"] for row in actors}
    # A recovery executor cannot count itself as the dead coordinator it fences.
    if executor_uid in actor_uids:
        executor_uid = ""
    executor_owners = {
        owner.get("uid")
        for pod in pods
        if pod.get("metadata", {}).get("uid") == executor_uid
        for owner in pod.get("metadata", {}).get("ownerReferences", [])
    }
    owner_uids = {owner["uid"] for row in actors for owner in row.get("owners", [])}
    child_uids = owner_uids | {
        job.get("metadata", {}).get("uid")
        for job in jobs
        if job.get("metadata", {}).get("labels", {}).get(_LABEL)
        == journal["operation_id"]
        and job.get("metadata", {}).get("uid") not in executor_owners
    }
    child_uids.discard(None)
    for pod in pods:
        metadata = pod.get("metadata", {})
        if metadata.get("uid") == executor_uid:
            continue
        is_holder = metadata.get("uid") in actor_uids or any(
            metadata.get("name") == row["name"]
            and metadata.get("namespace") == row["namespace"]
            for row in actors
        )
        is_child = metadata.get("labels", {}).get(_LABEL) == journal[
            "operation_id"
        ] or any(
            owner.get("uid") in child_uids
            for owner in metadata.get("ownerReferences", [])
        )
        if (is_holder or is_child) and not _terminal(pod):
            return False
    for job in jobs:
        metadata = job.get("metadata", {})
        if (
            metadata.get("uid") in executor_owners
            and metadata.get("uid") not in owner_uids
        ):
            continue
        selected = (
            metadata.get("uid") in owner_uids
            or metadata.get("labels", {}).get(_LABEL) == journal["operation_id"]
        )
        if selected and not _job_complete(job):
            if not job.get("spec", {}).get("suspend") or job.get("status", {}).get(
                "active", 0
            ):
                return False
    return True


def _matches(selector, labels):
    if not selector:
        return False
    if not all(
        labels.get(key) == value
        for key, value in selector.get("matchLabels", {}).items()
    ):
        return False
    for requirement in selector.get("matchExpressions", []):
        key, operator = requirement["key"], requirement["operator"]
        value = labels.get(key)
        values = requirement.get("values", [])
        if (
            operator == "In"
            and value not in values
            or operator == "NotIn"
            and value in values
            or operator == "Exists"
            and key not in labels
            or operator == "DoesNotExist"
            and key in labels
        ):
            return False
    return True


def shared_data_writers_stopped(snapshots, pods, jobs):
    for row in snapshots:
        for pod in pods:
            metadata = pod.get("metadata", {})
            if (
                metadata.get("namespace") == row["namespace"]
                and row["role"] in {"workload", "tuppr"}
                and _matches(row.get("selector", {}), metadata.get("labels", {}))
                and not _terminal(pod)
            ):
                return False
        if row["role"] == "cronjob":
            owned_jobs = [
                job
                for job in jobs
                if job.get("metadata", {}).get("namespace") == row["namespace"]
                and any(
                    owner.get("uid") == row["uid"]
                    for owner in job.get("metadata", {}).get("ownerReferences", [])
                )
            ]
            if any(not _job_complete(job) for job in owned_jobs):
                return False
            job_uids = {job.get("metadata", {}).get("uid") for job in owned_jobs}
            if any(
                not _terminal(pod)
                and any(
                    owner.get("uid") in job_uids
                    for owner in pod.get("metadata", {}).get("ownerReferences", [])
                )
                for pod in pods
            ):
                return False
    return True


def shared_data_upgrades_idle(resources):
    return all(
        row.get("status", {}).get("phase")
        in {"Completed", "Pending", "Suspended", "MaintenanceWindow"}
        for row in resources
    )


def shared_data_upgrade_workers_idle(resources, jobs, pods):
    """Tuppr 0.5.10 workers outlive the controller and may precede CR phase.

    Current owner UIDs correlate unlabelled workers; typed owner references and
    the upstream part-of/app labels retain correlation after CR recreation or
    deletion. Pod owners are matched to Job UIDs, never reused resource names.
    """
    upgrade_uids = {row.get("metadata", {}).get("uid") for row in resources}
    upgrade_uids.discard(None)
    upgrade_apps = {"talos-upgrade", "kubernetes-upgrade", "talos-upgrade-hook"}

    def source(metadata):
        labels = metadata.get("labels", {})
        return (
            labels.get("app.kubernetes.io/part-of") == "tuppr"
            and labels.get("app.kubernetes.io/name") in upgrade_apps
        )

    def owned(metadata):
        return any(
            owner.get("uid") in upgrade_uids
            or (
                owner.get("apiVersion", "").split("/")[0] == "tuppr.home-operations.com"
                and owner.get("kind") in {"TalosUpgrade", "KubernetesUpgrade"}
                and bool(owner.get("uid"))
            )
            for owner in metadata.get("ownerReferences", [])
        )

    selected = [
        job
        for job in jobs
        if source(job.get("metadata", {})) or owned(job.get("metadata", {}))
    ]
    if any(
        not _job_complete(job)
        or job.get("status", {}).get("active", 0)
        or job.get("status", {}).get("terminating", 0)
        for job in selected
    ):
        return False
    job_uids = {job.get("metadata", {}).get("uid") for job in selected}
    job_uids.discard(None)
    for pod in pods:
        metadata = pod.get("metadata", {})
        selected_pod = (
            source(metadata)
            or owned(metadata)
            or any(
                owner.get("uid") in job_uids
                for owner in metadata.get("ownerReferences", [])
            )
        )
        if selected_pod and not _terminal(pod):
            return False
    return True


def shared_data_sync_idle(resources):
    return all(
        not row.get("operation")
        and row.get("status", {}).get("operationState", {}).get("phase")
        not in {"Running", "Terminating"}
        for row in resources
    )


class FilterModule:
    def filters(self):
        return {
            name: value
            for name, value in globals().items()
            if name.startswith("shared_data_") and callable(value)
        }
