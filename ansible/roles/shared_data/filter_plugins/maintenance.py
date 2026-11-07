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
_LEASE_KINDS = _KINDS | {"cold-bootstrap", "node-operation"}
_LABEL = "home-ops/data-operation"
_SKIP = "argocd.argoproj.io/skip-reconcile"


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
    registry = {
        **registry,
        "consumers": {**registry["consumers"], **registry.get("file_consumers", {})},
    }
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
    maintenance = registry.get("maintenance", {})
    if not isinstance(maintenance, dict):
        raise ValueError("maintenance registry must be a mapping")
    operation_apps = maintenance.get("applications", [])
    if not isinstance(operation_apps, list) or any(
        not isinstance(app, str) or not _OPERATION.fullmatch(app)
        for app in operation_apps
    ):
        raise ValueError("operation application names must be registered DNS names")
    for app in dict.fromkeys([*apps, *operation_apps, "tuppr"]):
        if (
            app != "tuppr"
            and app not in registry["consumers"]
            and app not in operation_apps
        ):
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
    for cron in maintenance.get("cronjobs", []):
        if not isinstance(cron, dict) or not all(
            isinstance(cron.get(key), str) and _OPERATION.fullmatch(cron[key])
            for key in ["name", "namespace"]
        ):
            raise ValueError("operation schedulers require explicit namespace/name")
        targets.append(
            {
                "api_version": "batch/v1",
                "kind": "CronJob",
                "namespace": cron["namespace"],
                "name": cron["name"],
                "role": "cronjob",
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
    if role in {"root", "application"}:
        annotations = metadata.get("annotations", {})
        result["skip_reconcile"] = {
            "present": _SKIP in annotations,
            "value": deepcopy(annotations.get(_SKIP)),
            "annotations_present": "annotations" in metadata,
        }
    if role in {"workload", "tuppr"}:
        result["selector"] = deepcopy(spec.get("selector", {}))
        if not result["selector"]:
            raise ValueError("writer has no pod selector")
    return result


def shared_data_snapshot_restored(snapshot, current):
    if current.get("metadata", {}).get("uid") != snapshot["uid"]:
        return False
    if "skip_reconcile" in snapshot:
        annotations = current.get("metadata", {}).get("annotations", {})
        skip = snapshot["skip_reconcile"]
        if (_SKIP in annotations) != skip["present"] or (
            skip["present"] and annotations[_SKIP] != skip["value"]
        ):
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
    if snapshot["role"] in {"root", "application"}:
        if restore and not shared_data_sync_idle([current]):
            raise ValueError(
                "held Application has an active or queued sync; inspect before resuming"
            )
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
    if restore and "skip_reconcile" in snapshot:
        skip = snapshot["skip_reconcile"]
        annotations = metadata.get("annotations", {})
        path = "/metadata/annotations/" + _SKIP.replace("/", "~1")
        if skip["present"]:
            if "annotations" not in metadata:
                patch.append(
                    {"op": "add", "path": "/metadata/annotations", "value": {}}
                )
            patch.append({"op": "add", "path": path, "value": skip["value"]})
        elif _SKIP in annotations:
            if not skip["annotations_present"] and set(annotations) == {_SKIP}:
                patch.append({"op": "remove", "path": "/metadata/annotations"})
            else:
                patch.append({"op": "remove", "path": path})
    return patch


def shared_data_skip_patch(snapshot, current):
    """Stop reconciliation only after a fresh, identity-bound idle observation."""
    if (
        snapshot["role"] not in {"root", "application"}
        or "skip_reconcile" not in snapshot
    ):
        raise ValueError("Application skip requires its recorded original annotation")
    if not current.get("metadata", {}).get("resourceVersion"):
        raise ValueError("Application idle skip requires an observed resourceVersion")
    # These tests bind both the idle observation and automation fence to this patch.
    patch = shared_data_patch(snapshot, current)
    if not shared_data_sync_idle([current]):
        raise ValueError(
            "Application sync is active or queued; cannot freeze reconciliation"
        )
    if "automated" in current.get("spec", {}).get("syncPolicy", {}):
        raise ValueError(
            "Application automation fence changed before reconciliation hold"
        )
    patch = [row for row in patch if row["op"] == "test"]
    if "annotations" not in current["metadata"]:
        patch.append({"op": "add", "path": "/metadata/annotations", "value": {}})
    patch.append(
        {
            "op": "add",
            "path": "/metadata/annotations/" + _SKIP.replace("/", "~1"),
            "value": "true",
        }
    )
    return patch


def shared_data_compensation_ready(resources):
    """Already skipped requests stay parked; unskipped operations must finish."""
    return all(
        row.get("metadata", {}).get("annotations", {}).get(_SKIP) == "true"
        or shared_data_sync_idle([row])
        for row in resources
    )


def shared_data_compensation_skip_patch(snapshot, current):
    """Re-hold without unfreezing or deleting an already skipped foreign request."""
    if current.get("metadata", {}).get("annotations", {}).get(_SKIP) == "true":
        return shared_data_patch(snapshot, current)
    return shared_data_skip_patch(snapshot, current)


def shared_data_application_held(snapshot, current):
    return (
        current.get("metadata", {}).get("uid") == snapshot["uid"]
        and current.get("metadata", {}).get("annotations", {}).get(_SKIP) == "true"
        and "automated" not in current.get("spec", {}).get("syncPolicy", {})
        and shared_data_sync_idle([current])
    )


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
        if record["operation_kind"] not in _LEASE_KINDS or record["stage"] not in {
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


def _ready_node(node):
    return (
        bool(node.get("metadata", {}).get("uid"))
        and any(
            row.get("type") == "Ready" and row.get("status") == "True"
            for row in node.get("status", {}).get("conditions", [])
        )
        and not any(
            row.get("key")
            in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
            for row in node.get("spec", {}).get("taints", [])
        )
    )


def _actor_node(actor):
    bindings = actor.get("fence_nodes")
    if (
        actor.get("kind", "Pod") != "Pod"
        or not isinstance(bindings, list)
        or len(bindings) != 1
        or not isinstance(bindings[0], dict)
        or any(
            not isinstance(bindings[0].get(key), str) or not bindings[0][key].strip()
            for key in ("name", "uid")
        )
    ):
        raise ValueError(
            "historical Pod executor lacks authenticated original node identity"
        )
    return bindings[0]


def shared_data_executor_actor(pod, node, sa, ssr):
    """Bind an actual projected-token Pod/SA to its signed original Ready node."""
    meta = pod.get("metadata", {})
    user = ssr.get("status", {}).get("userInfo", {})
    extra = user.get("extra", {})
    if not isinstance(extra, dict):
        raise ValueError("API-authenticated bound Pod identity is required")
    claims = {}
    for key in ("pod-name", "pod-uid", "node-name", "node-uid"):
        values = extra.get("authentication.kubernetes.io/" + key)
        if (
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], str)
            or not values[0].strip()
        ):
            raise ValueError(
                "nonempty unambiguous authenticated Pod/original node claims are required"
            )
        claims[key] = values[0]
    sa_meta = sa.get("metadata", {})
    if (
        not sa_meta.get("uid")
        or user.get("uid") != sa_meta["uid"]
        or user.get("username")
        != "system:serviceaccount:"
        + meta.get("namespace", "")
        + ":"
        + sa_meta.get("name", "")
        or sa_meta.get("namespace") != meta.get("namespace")
        or sa_meta.get("name") != pod.get("spec", {}).get("serviceAccountName")
        or claims["pod-name"] != meta.get("name")
        or claims["pod-uid"] != meta.get("uid")
    ):
        raise ValueError("API-authenticated bound Pod/ServiceAccount identity differs")
    if (
        not _ready_node(node)
        or claims["node-name"] != pod.get("spec", {}).get("nodeName")
        or claims["node-name"] != node.get("metadata", {}).get("name")
        or claims["node-uid"] != node["metadata"]["uid"]
    ):
        raise ValueError(
            "authenticated original node differs from the assigned Ready node"
        )
    if meta.get("deletionTimestamp") or pod.get("status", {}).get("phase") != "Running":
        raise ValueError("a live executor Pod is required")
    return {
        "kind": "Pod",
        "uid": meta["uid"],
        "name": meta["name"],
        "namespace": meta["namespace"],
        "owners": deepcopy(meta.get("ownerReferences", [])),
        "fence_nodes": [{"name": claims["node-name"], "uid": claims["node-uid"]}],
    }


def shared_data_executor_current(lease, actor, nodes):
    """Renewals never rebind a historical actor to a replacement node."""
    if shared_data_lease_record(lease).get("actor") != actor:
        return False
    try:
        _fence_nodes([actor], nodes)
    except ValueError, TypeError, KeyError:
        return False
    return True


def _historical_actors(journal, record):
    actors = [
        journal[key]
        for key in ("holder", "coordinator", "lease_coordinator")
        if journal.get(key)
    ]
    actors += record.get("fence_actors", [])
    if record.get("actor"):
        actors.append(record["actor"])
    unique = {}
    for actor in actors:
        if not actor.get("uid"):
            raise ValueError("historical executor identity is ambiguous")
        if actor["uid"] in unique and unique[actor["uid"]] != actor:
            raise ValueError("historical executor binding changed")
        unique[actor["uid"]] = actor
    return list(unique.values())


def _fence_nodes(actors, nodes):
    current = {node.get("metadata", {}).get("name"): node for node in nodes}
    if len(current) != len(nodes):
        raise ValueError("node identity is ambiguous")
    bindings = {}
    for actor in actors:
        binding = _actor_node(actor)
        name, uid = binding["name"], binding["uid"]
        if (
            name in bindings
            and bindings[name] != uid
            or name not in current
            or current[name].get("metadata", {}).get("uid") != uid
            or not _ready_node(current[name])
        ):
            raise ValueError(
                "historical original node identity changed, disappeared or is not Ready"
            )
        bindings[name] = uid
    if not bindings:
        raise ValueError("historical original node identity is required")
    return [{"name": name, "uid": uid} for name, uid in sorted(bindings.items())]


def _upload_binding(upload):
    if upload.get("node_binding") != "coordinator-assigned-before-start" or not all(
        upload.get(key) for key in ("uid", "name", "namespace")
    ):
        raise ValueError(
            "upload child lacks durable original node binding before execution"
        )
    return _actor_node({**upload, "kind": "Pod"})


def _fencing_history(journal, actors, pods, jobs, nodes, executor_uid=""):
    bindings = _fence_nodes(actors, nodes)
    actor_by_uid = {actor["uid"]: actor for actor in actors}
    owner_uids = {
        owner.get("uid") for actor in actors for owner in actor.get("owners", [])
    }
    own_jobs = {
        owner.get("uid")
        for pod in pods
        if pod.get("metadata", {}).get("uid") == executor_uid
        for owner in pod.get("metadata", {}).get("ownerReferences", [])
    }
    upload = journal.get("upload_job", {})
    upload_node = None
    if upload:
        upload_node = _upload_binding(upload)
        _fence_nodes([{**upload, "kind": "Pod"}], nodes)
        if upload_node not in bindings:
            bindings.append(upload_node)
    selected_jobs = set(owner_uids)
    if upload:
        selected_jobs.add(upload["uid"])
    for job in jobs:
        meta = job.get("metadata", {})
        if meta.get("uid") in own_jobs and meta.get("uid") not in owner_uids:
            continue
        bound_upload = upload and (
            meta.get("uid") == upload["uid"]
            or (meta.get("name"), meta.get("namespace"))
            == (upload["name"], upload["namespace"])
        )
        if bound_upload:
            if (
                any(
                    meta.get(key) != upload.get(key)
                    for key in ("uid", "name", "namespace")
                )
                or meta.get("labels", {}).get(_LABEL) != journal["operation_id"]
                or job.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("nodeName")
                != upload_node["name"]
            ):
                raise ValueError(
                    "durably bound upload child Job identity or assignment was replaced"
                )
        elif (
            meta.get("labels", {}).get(_LABEL) == journal["operation_id"]
            and meta.get("uid") not in owner_uids
        ):
            raise ValueError(
                "child Job lacks durable original node binding before execution"
            )
    for pod in pods:
        meta = pod.get("metadata", {})
        uid = meta.get("uid")
        if uid == executor_uid and uid not in actor_by_uid:
            continue
        actor = actor_by_uid.get(uid)
        for old in actors:
            if (meta.get("name"), meta.get("namespace")) == (
                old["name"],
                old["namespace"],
            ) and uid != old["uid"]:
                raise ValueError("coordinator immutable identity was replaced")
        selected = (
            actor
            or meta.get("labels", {}).get(_LABEL) == journal["operation_id"]
            or any(
                owner.get("uid") in selected_jobs
                for owner in meta.get("ownerReferences", [])
            )
        )
        if not selected:
            continue
        if actor:
            expected = _actor_node(actor)
        elif upload and any(
            owner.get("uid") == upload.get("uid") and owner.get("kind") == "Job"
            for owner in meta.get("ownerReferences", [])
        ):
            expected = upload_node
        else:
            raise ValueError(
                "child Pod lacks authenticated or pre-execution original node binding"
            )
        if pod.get("spec", {}).get("nodeName") != expected["name"]:
            raise ValueError(
                "historical Pod assignment differs from original node binding"
            )
    return bindings


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
    if "home-ops/native-operation" in lease.get("metadata", {}).get("finalizers", []):
        raise ValueError("native CLI ownership requires inspected manual resolution")
    spec = lease.get("spec", {})
    if spec.get("holderIdentity", "") != expected_identity:
        raise ValueError("Lease ownership changed before acquisition or recovery")
    if not all(actor.get(key) for key in ("uid", "name", "namespace")):
        raise ValueError("live executor identity is required")
    _actor_node(actor)
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
    previous = shared_data_lease_record(lease)
    history = []
    if expected_identity:
        if (
            not previous
            or previous["operation_id"] != operation_id
            or previous["operation_kind"] != operation_kind
        ):
            raise ValueError("existing Lease lacks matching durable executor binding")
        history = _historical_actors({}, previous)
        for old in history:
            _actor_node(old)
            if old["uid"] == actor["uid"] and old != actor:
                raise ValueError("executor original node binding cannot be replaced")
        history = [old for old in history if old["uid"] != actor["uid"]]
    annotations[_LEASE_RECORD] = json.dumps(
        {
            "operation_id": operation_id,
            "operation_kind": operation_kind,
            "actor": deepcopy(actor),
            "stage": stage,
            "fence_actors": history,
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


def shared_data_orphan_releasable(lease, pods, jobs, now, executor_uid="", nodes=None):
    record = shared_data_lease_record(lease)
    if (
        not record
        or record["stage"] != "claimed"
        or not shared_data_lease_expired(lease, now)
    ):
        return False
    return shared_data_coordinator_fenced(
        {
            "operation_id": record["operation_id"],
            "holder": record["actor"],
            "fence_actors": record.get("fence_actors", []),
        },
        pods,
        jobs,
        executor_uid,
        nodes,
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
    journal, lease, pods, jobs, now, inspected=False, executor_uid="", nodes=None
):
    actor = _effective_coordinator(journal, lease)
    if journal.get("phase") != "complete" or not actor:
        return False
    if not inspected and not shared_data_lease_expired(lease, now):
        return False
    return shared_data_coordinator_fenced(
        {
            **journal,
            "lease_coordinator": actor,
            "fence_actors": shared_data_lease_record(lease).get("fence_actors", []),
        },
        pods,
        jobs,
        executor_uid,
        nodes,
    )


def _terminal(pod):
    # Terminating is not terminated, including NFS-hung pods.
    return pod.get("status", {}).get("phase") in {"Succeeded", "Failed"}


def _job_complete(job):
    return any(
        row.get("type") in {"Complete", "Failed"} and row.get("status") == "True"
        for row in job.get("status", {}).get("conditions", [])
    )


def shared_data_operation_jobs_stopped(
    pods, jobs, executor_uid, namespace="selfhosted"
):
    """Fence manual coordinators/uploaders as well as registered CronJob work."""
    own_jobs = {
        owner.get("uid")
        for pod in pods
        if pod.get("metadata", {}).get("uid") == executor_uid
        for owner in pod.get("metadata", {}).get("ownerReferences", [])
        if owner.get("kind") == "Job"
    }
    selected = set()
    for job in jobs:
        metadata = job.get("metadata", {})
        labels = metadata.get("labels", {})
        if not (
            labels.get(_LABEL) or labels.get("app.kubernetes.io/name") == "shared-data"
        ):
            continue
        if metadata.get("namespace") == namespace and any(
            owner.get("kind") == "CronJob"
            and owner.get("name") == "shared-data-watchdog"
            for owner in metadata.get("ownerReferences", [])
        ):
            continue
        uid = metadata.get("uid")
        if not uid:
            return False
        selected.add(uid)
        if uid not in own_jobs and (
            job.get("status", {}).get("active", 0)
            or job.get("status", {}).get("terminating", 0)
        ):
            return False
        if (
            uid not in own_jobs
            and not _job_complete(job)
            and not (
                job.get("spec", {}).get("suspend")
                and not job.get("status", {}).get("active", 0)
            )
        ):
            return False
    return all(
        _terminal(pod) or pod.get("metadata", {}).get("uid") == executor_uid
        for pod in pods
        if any(
            owner.get("uid") in selected
            for owner in pod.get("metadata", {}).get("ownerReferences", [])
        )
    )


def shared_data_upload_claim_terminal(claim, jobs, pods, nodes):
    expected = claim.get("upload_job", {})
    try:
        binding = _upload_binding(expected)
        _fence_nodes([{**expected, "kind": "Pod"}], nodes)
    except ValueError, KeyError, TypeError:
        return False
    if len(jobs) != 1 or not nodes:
        return False
    job = jobs[0]
    if (
        job.get("spec", {}).get("template", {}).get("spec", {}).get("nodeName")
        != binding["name"]
    ):
        return False
    metadata = job.get("metadata", {})
    if any(
        metadata.get(key) != expected.get(key) for key in ["uid", "name", "namespace"]
    ) or metadata.get("labels", {}).get(_LABEL) != claim.get("operation"):
        return False
    if (
        not any(
            row.get("type") == "Complete" and row.get("status") == "True"
            for row in job.get("status", {}).get("conditions", [])
        )
        or job.get("status", {}).get("active", 0)
        or job.get("status", {}).get("terminating", 0)
    ):
        return False
    if any(
        not any(
            row.get("type") == "Ready" and row.get("status") == "True"
            for row in node.get("status", {}).get("conditions", [])
        )
        or any(
            taint.get("key")
            in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
            for taint in node.get("spec", {}).get("taints", [])
        )
        for node in nodes
    ):
        return False
    return all(
        _terminal(pod) and pod.get("spec", {}).get("nodeName") == binding["name"]
        for pod in pods
        if any(
            owner.get("uid") == expected["uid"]
            for owner in pod.get("metadata", {}).get("ownerReferences", [])
        )
    )


def shared_data_recovery_fenced(
    journal, lease, pods, jobs, executor_uid="", nodes=None
):
    coordinator = _effective_coordinator(journal, lease)
    return bool(coordinator) and shared_data_coordinator_fenced(
        {
            **journal,
            "lease_coordinator": coordinator,
            "fence_actors": shared_data_lease_record(lease).get("fence_actors", []),
        },
        pods,
        jobs,
        executor_uid,
        nodes,
    )


def shared_data_recovery(journal, lease, pods, jobs, now, executor_uid="", nodes=None):
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
        {
            **journal,
            "lease_coordinator": coordinator,
            "fence_actors": shared_data_lease_record(lease).get("fence_actors", []),
        },
        pods,
        jobs,
        executor_uid,
        nodes,
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


def shared_data_coordinator_fenced(journal, pods, jobs, executor_uid="", nodes=None):
    try:
        actors = _historical_actors(
            journal, {"fence_actors": journal.get("fence_actors", [])}
        )
        _fencing_history(journal, actors, pods, jobs, nodes or [], executor_uid)
    except ValueError, KeyError, TypeError:
        return False
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
    if journal.get("upload_job"):
        child_uids.add(journal["upload_job"]["uid"])
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
            metadata.get("uid") in child_uids
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


def shared_data_writers_stopped(snapshots, pods, jobs, executor_uid=""):
    executor_owners = {
        owner.get("uid")
        for pod in pods
        if pod.get("metadata", {}).get("uid") == executor_uid
        and pod.get("status", {}).get("phase") == "Running"
        and not pod.get("metadata", {}).get("deletionTimestamp")
        for owner in pod.get("metadata", {}).get("ownerReferences", [])
        if owner.get("kind") == "Job"
    }
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
            if any(
                not _job_complete(job)
                for job in owned_jobs
                if job.get("metadata", {}).get("uid") not in executor_owners
            ):
                return False
            job_uids = {job.get("metadata", {}).get("uid") for job in owned_jobs}
            if any(
                not _terminal(pod)
                and pod.get("metadata", {}).get("uid") != executor_uid
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


def shared_data_watchdog_fence(journal, lease, pods, jobs, nodes, now, executor_uid):
    """Plan only identity-checked stale actor fencing; tasks own API mutations.

    Healthy nodes are required both before deletion and after the disappearance
    barrier. No force deletion or name-only Pod replacement is accepted.
    """
    if not shared_data_lease_expired(lease, now):
        return {"jobs": [], "pods": [], "expired": False}
    record = shared_data_lease_record(lease)
    if (
        record.get("operation_kind") == "cold-bootstrap"
        or record.get("actor", {}).get("kind", "Pod") != "Pod"
    ):
        raise ValueError(
            "cold or non-Pod executor requires explicit exact bootstrap fencing; watchdog cannot resume it"
        )

    if not record:
        raise ValueError("stale Lease lacks an immutable coordinator claim")
    if journal and journal.get("phase") != "complete":
        actor = _effective_coordinator(journal, lease)
        if not actor:
            raise ValueError("Lease and journal ownership conflict")
        operation = journal["operation_id"]
        actors = [
            journal["holder"],
            journal.get("coordinator", journal["holder"]),
            actor,
        ]
    else:
        actor = record["actor"]
        operation = record["operation_id"]
        actors = [actor]
    actors += record.get("fence_actors", [])
    actors = _historical_actors({"holder": actor}, {"fence_actors": actors})
    fence_journal = journal if journal.get("operation_id") == operation else {}
    original_nodes = _fencing_history(
        {**fence_journal, "operation_id": operation},
        actors,
        pods,
        jobs,
        nodes,
        executor_uid,
    )
    actor_uids = {row["uid"] for row in actors}
    if not executor_uid or executor_uid in actor_uids:
        raise ValueError("watchdog must be distinct from historical coordinators")
    healthy = {
        node["metadata"]["name"]
        for node in nodes
        if any(
            row.get("type") == "Ready" and row.get("status") == "True"
            for row in node.get("status", {}).get("conditions", [])
        )
        and not any(
            row.get("key")
            in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
            for row in node.get("spec", {}).get("taints", [])
        )
    }
    if not nodes or len(healthy) != len(nodes):
        raise ValueError("node health is uncertain; do not infer storage work stopped")
    watchdog_owners = {
        owner.get("uid")
        for pod in pods
        if pod.get("metadata", {}).get("uid") == executor_uid
        for owner in pod.get("metadata", {}).get("ownerReferences", [])
    }
    actor_owners = {owner["uid"] for row in actors for owner in row.get("owners", [])}
    if actor_owners & watchdog_owners:
        raise ValueError("watchdog cannot fence its own controller")
    selected_jobs = [
        job
        for job in jobs
        if job.get("metadata", {}).get("uid") in actor_owners
        or (
            job.get("metadata", {}).get("labels", {}).get(_LABEL) == operation
            and job.get("metadata", {}).get("uid") not in watchdog_owners
        )
    ]
    job_uids = {job["metadata"]["uid"] for job in selected_jobs}
    if fence_journal.get("upload_job"):
        job_uids.add(fence_journal["upload_job"]["uid"])
    selected_pods = []
    for pod in pods:
        meta = pod.get("metadata", {})
        if meta.get("uid") == executor_uid:
            continue
        for historical in actors:
            if (meta.get("name"), meta.get("namespace")) == (
                historical["name"],
                historical["namespace"],
            ) and meta.get("uid") != historical["uid"]:
                raise ValueError(
                    "coordinator name was replaced with a different immutable identity"
                )
        if (
            meta.get("uid") in actor_uids
            or meta.get("labels", {}).get(_LABEL) == operation
            or any(
                owner.get("uid") in job_uids
                for owner in meta.get("ownerReferences", [])
            )
        ):
            if pod.get("spec", {}).get("nodeName") not in healthy and not _terminal(
                pod
            ):
                # Pending unscheduled Pods are safely deletable, provided they
                # cannot be recreated by an unsuspended controller.
                if (
                    pod.get("spec", {}).get("nodeName")
                    or pod.get("status", {}).get("phase") != "Pending"
                ):
                    raise ValueError("coordinator node is not proven healthy")
            selected_pods.append(pod)
    for row in selected_jobs + selected_pods:
        if not all(
            row.get("metadata", {}).get(key)
            for key in ["name", "namespace", "uid", "resourceVersion"]
        ):
            raise ValueError("fencing requires complete immutable resource identity")
    return {
        "jobs": selected_jobs,
        "pods": selected_pods,
        "expired": True,
        "actors": actors,
        "operation_id": operation,
        "nodes": original_nodes,
        "upload_job": deepcopy(fence_journal.get("upload_job", {})),
    }


def shared_data_fence_claim(lease, journal, actor, now, duration=300):
    """CAS stale ownership while retaining actors across every crash window."""
    if not shared_data_lease_expired(lease, now):
        raise ValueError("only an expired Lease permits automatic fencing takeover")
    record = shared_data_lease_record(lease)
    if not record:
        raise ValueError("stale Lease lacks a verified claim")
    actors = list(record.get("fence_actors", [])) + [record["actor"]]
    if journal and journal.get("phase") != "complete":
        if not _effective_coordinator(journal, lease):
            raise ValueError("Lease and journal ownership conflict")
        actors += [journal["holder"], journal.get("coordinator", journal["holder"])]
    unique = {row["uid"]: deepcopy(row) for row in actors}
    if actor["uid"] in unique:
        raise ValueError("fencing actor must be a distinct live Pod")
    patch = shared_data_lease_takeover(
        lease,
        lease["spec"]["holderIdentity"],
        record["operation_id"],
        record["operation_kind"],
        actor,
        now,
        duration,
        record["stage"],
    )
    annotations = patch[-1]["value"]
    claimed = json.loads(annotations[_LEASE_RECORD])
    claimed["fence_actors"] = list(unique.values())
    annotations[_LEASE_RECORD] = json.dumps(claimed, sort_keys=True)
    return patch


def shared_data_fence_complete(plan, pods, jobs, nodes, executor_uid):
    if not plan.get("expired") or not nodes:
        return False
    for node in nodes:
        if not any(
            row.get("type") == "Ready" and row.get("status") == "True"
            for row in node.get("status", {}).get("conditions", [])
        ):
            return False
        if any(
            row.get("key")
            in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
            for row in node.get("spec", {}).get("taints", [])
        ):
            return False
    try:
        bindings = _fencing_history(
            {
                "operation_id": plan["operation_id"],
                "upload_job": plan.get("upload_job", {}),
            },
            plan["actors"],
            pods,
            jobs,
            nodes,
            executor_uid,
        )
        if bindings != plan.get("nodes"):
            return False
    except ValueError, KeyError, TypeError:
        return False
    return shared_data_coordinator_fenced(
        {
            "operation_id": plan["operation_id"],
            "holder": plan["actors"][0],
            "fence_actors": plan["actors"][1:],
            "upload_job": plan.get("upload_job", {}),
        },
        pods,
        jobs,
        executor_uid,
        nodes,
    )
