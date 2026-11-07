"""Fixed native operation exclusion; this owner is never Pod-fenceable."""

import json
from copy import deepcopy
from datetime import datetime, timezone

RECORD = "home-ops/data-coordinator"
FINALIZER = "home-ops/native-operation"
ACTIONS = {
    "talos-apply",
    "talos-bootstrap",
    "talos-upgrade",
    "talos-upgrade-k8s",
    "talos-reset",
    "platform-bootstrap",
    "platform-destroy",
    "cluster-create",
    "cluster-destroy",
}


def node_operation_node(nodes, address="", original=None):
    matches = [
        n
        for n in nodes
        if not address
        or n["metadata"]["name"] == address
        or any(
            a.get("type") == "InternalIP" and a.get("address") == address
            for a in n.get("status", {}).get("addresses", [])
        )
    ]
    if len(matches) != 1:
        raise ValueError("one unambiguous original node is required")
    node = matches[0]
    binding = {key: node["metadata"][key] for key in ("name", "uid")}
    if not binding["uid"] or original and binding != original:
        raise ValueError("original node identity changed")
    if not any(
        c.get("type") == "Ready" and c.get("status") == "True"
        for c in node.get("status", {}).get("conditions", [])
    ) or any(
        t.get("key")
        in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
        for t in node.get("spec", {}).get("taints", [])
    ):
        raise ValueError("original node is not Ready")
    return binding


def node_operation_available(lease, journal, cold):
    if FINALIZER in lease.get("metadata", {}).get("finalizers", []):
        raise ValueError("native gate is retained for unresolved local execution")
    if lease.get("spec", {}).get("holderIdentity", ""):
        raise ValueError(
            "shared maintenance Lease is held; expiration never fences native work"
        )
    if journal and journal.get("phase") != "complete":
        raise ValueError("unfinished maintenance journal requires inspection")
    if cold:
        admission = cold.get("admission", {})
        if (
            cold.get("phase") != "admitted"
            or admission.get("global_root_allowed") is not True
            or admission.get("unadmitted_apps") != []
            or any(admission.get(k) != cold.get(k) for k in ("revision", "apps"))
            or admission.get("cold_token") != cold.get("token")
        ):
            raise ValueError("unfinished cold recovery cannot be bypassed")
    return True


def node_operation_claim(lease, operation, actor, action, now, duration):
    if lease.get("metadata", {}).get("deletionTimestamp") or lease.get("spec", {}).get(
        "holderIdentity", ""
    ):
        raise ValueError("shared Lease changed before native acquisition")
    if (
        action not in ACTIONS
        or actor.get("kind") != "NativeCLI"
        or not actor.get("uid")
    ):
        raise ValueError("fixed native operation and invocation identity required")
    if not 3600 <= int(duration) <= 43200:
        raise ValueError("native outage coverage must be between one and twelve hours")
    stamp = (
        datetime.fromtimestamp(float(now), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    record = {
        "operation_id": operation,
        "operation_kind": "node-operation",
        "actor": actor,
        "stage": "claimed",
        "action": action,
    }
    return [
        {"op": "test", "path": "/metadata/uid", "value": lease["metadata"]["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": lease["metadata"]["resourceVersion"],
        },
        *(
            [{"op": "test", "path": "/spec", "value": deepcopy(lease["spec"])}]
            if "spec" in lease
            else []
        ),
        {
            "op": "add",
            "path": "/metadata/finalizers",
            "value": list(
                dict.fromkeys(
                    [*lease.get("metadata", {}).get("finalizers", []), FINALIZER]
                )
            ),
        },
        {
            "op": "add",
            "path": "/spec",
            "value": {
                **lease.get("spec", {}),
                "holderIdentity": operation + ":" + actor["uid"],
                "leaseDurationSeconds": int(duration),
                "renewTime": stamp,
                "acquireTime": stamp,
                "leaseTransitions": int(
                    lease.get("spec", {}).get("leaseTransitions", 0)
                )
                + 1,
            },
        },
        {
            "op": "add",
            "path": "/metadata/annotations",
            "value": {
                **lease.get("metadata", {}).get("annotations", {}),
                RECORD: json.dumps(record, sort_keys=True),
            },
        },
    ]


def node_operation_owned(lease, original, actor, operation):
    entry = json.loads(
        lease.get("metadata", {}).get("annotations", {}).get(RECORD, "{}")
    )
    if (
        lease.get("metadata", {}).get("uid") != original
        or entry.get("actor") != actor
        or FINALIZER not in lease.get("metadata", {}).get("finalizers", [])
        or entry.get("operation_kind") != "node-operation"
        or entry.get("operation_id") != operation
        or lease.get("spec", {}).get("holderIdentity") != operation + ":" + actor["uid"]
    ):
        raise ValueError("native invocation lost exact shared Lease ownership")
    return True


def _native_rows(rows, node):
    if any(
        not isinstance(r, dict)
        or r.get("node") != node
        or not isinstance(r.get("spec"), dict)
        for r in rows
    ):
        raise ValueError("native resource inventory has an ambiguous node or shape")
    return rows


def node_operation_blank_disk(status, volumes, node, disk):
    _native_rows(status, node)
    _native_rows(volumes, node)
    if len(status) != 1 or status[0]["spec"].get("stage") != "maintenance":
        raise ValueError("positive native maintenance stage is required")
    matches = [r for r in volumes if r["spec"].get("dev_path") == disk]
    if (
        len(matches) != 1
        or matches[0]["spec"].get("type") != "disk"
        or matches[0]["spec"].get("size", 0) <= 0
    ):
        raise ValueError("one positively discovered installation disk is required")
    target = matches[0]
    if any(
        target["spec"].get(k)
        for k in (
            "name",
            "uuid",
            "label",
            "partition_label",
            "partition_uuid",
            "partition_type",
            "parent",
        )
    ):
        raise ValueError("installation disk contains a filesystem or partition layout")
    if any(
        r["spec"].get("parent_dev_path") == disk
        or r["spec"].get("parent") == target.get("metadata", {}).get("id")
        for r in volumes
        if r is not target
    ):
        raise ValueError("installation disk has child partitions")
    if any(
        r["spec"].get(k) in {"STATE", "EPHEMERAL"}
        for r in volumes
        for k in ("label", "partition_label")
    ):
        raise ValueError("existing Talos state or etcd storage refuses fresh creation")
    return True


def _ordinary_directory(listing, name, node):
    lines = listing.strip().splitlines()
    if not lines or lines[0].split() != [
        "NODE",
        "MODE",
        "UID",
        "GID",
        "SIZE(B)",
        "LASTMOD",
        "LABEL",
        "NAME",
    ]:
        raise ValueError("unsupported native directory inventory")
    rows = [line.split() for line in lines[1:]]
    matches = [r for r in rows if r and r[-1] == name]
    if (
        len(matches) != 1
        or matches[0][0] != node
        or not matches[0][1].startswith("d")
        or "->" in matches[0]
    ):
        raise ValueError("etcd path is absent, ambiguous or not an ordinary directory")


def node_operation_empty_etcd_mount(mounts, members, node, var_listing, lib_listing):
    _native_rows(mounts, node)
    _native_rows(members, node)
    if members:
        raise ValueError("local etcd membership already exists")
    ephemeral = [r for r in mounts if r["spec"].get("target") == "/var"]
    if (
        len(ephemeral) != 1
        or ephemeral[0]["spec"].get("spec", {}).get("volumeID") != "EPHEMERAL"
        or not ephemeral[0]["spec"].get("source", "").startswith("/dev/")
        or ephemeral[0]["spec"].get("detached", False)
    ):
        raise ValueError("mounted EPHEMERAL at /var is required")
    if any(
        r["spec"].get("target", "").rstrip("/") in {"/var/lib", "/var/lib/etcd"}
        or r["spec"].get("target", "").startswith("/var/lib/etcd/")
        for r in mounts
    ):
        raise ValueError("nested mount shadows the inspected etcd directory")
    _ordinary_directory(var_listing, ".", node)
    _ordinary_directory(var_listing, "lib", node)
    _ordinary_directory(lib_listing, ".", node)
    _ordinary_directory(lib_listing, "etcd", node)
    return True


def node_operation_retained(namespace, root, source, now, proof=None):
    if namespace.get("metadata", {}).get("deletionTimestamp"):
        raise ValueError("coordination namespace is already terminating")
    key = "argocd.argoproj.io/sync-options"
    if "Delete=false" not in namespace.get("metadata", {}).get("annotations", {}).get(
        key, ""
    ).split(","):
        raise ValueError("coordination namespace retention must already be adopted")
    if (
        source.get("kind") != "Namespace"
        or source.get("metadata", {}).get("name") != "selfhosted"
        or "Delete=false"
        not in source.get("metadata", {}).get("annotations", {}).get(key, "").split(",")
    ):
        raise ValueError("last successful root source does not retain coordination")
    status = root.get("status", {})
    operation = status.get("operationState", {})
    if operation.get("phase") != "Succeeded":
        raise ValueError("root must have successfully adopted retained source")
    sync_state = status.get("sync", {}).get("status")
    if proof is None:
        if sync_state != "Synced":
            raise ValueError("root must have successfully adopted retained source")
    else:
        root_spec = deepcopy(root.get("spec", {}))
        root_spec.pop("syncPolicy", None)
        if (
            root.get("metadata", {}).get("uid") != proof["root_uid"]
            or root_spec != proof["root_source_spec"]
            or namespace.get("metadata", {}).get("uid") != proof["namespace_uid"]
            or namespace.get("metadata", {}).get("resourceVersion")
            != proof["namespace_resource_version"]
            or source != proof["namespace_source"]
            or operation.get("finishedAt") != proof["finished_at"]
        ):
            raise ValueError("retention adoption identity, source or namespace changed")
        if sync_state == "OutOfSync":
            resources = status.get("resources", [])
            drift = [row for row in resources if row.get("status") == "OutOfSync"]
            if (
                not proof["owned_appset_policy_change"]
                or not drift
                or any(
                    row.get("status") not in {"Synced", "OutOfSync"}
                    for row in resources
                )
                or any(
                    (
                        row.get("group"),
                        row.get("kind"),
                        row.get("namespace"),
                        row.get("name"),
                    )
                    != ("argoproj.io", "ApplicationSet", "argocd", "apps")
                    for row in drift
                )
            ):
                raise ValueError(
                    "Root drift is not attributable solely to the owned ApplicationSet fence"
                )
        elif sync_state != "Synced":
            raise ValueError("Root sync state is unknown after retention adoption")
    stamp = datetime.fromisoformat(
        operation["finishedAt"].replace("Z", "+00:00")
    ).timestamp()
    if float(now) - stamp < 300:
        raise ValueError(
            "retention adoption must precede deletion by at least five minutes"
        )
    revisions = status.get("sync", {}).get(
        "revisions", [status.get("sync", {}).get("revision", "")]
    )
    applied = operation.get("syncResult", {}).get(
        "revisions", [operation.get("syncResult", {}).get("revision", "")]
    )
    if (
        len(set(revisions)) != 1
        or revisions != applied
        or (proof is not None and revisions != proof["revisions"])
    ):
        raise ValueError(
            "current root revision differs from successful adopted revision"
        )
    return True


def node_operation_retention_proof(namespace, root, source, now, appset):
    """Persist successful adoption before our own policy writes can alter status."""
    node_operation_retained(namespace, root, source, now)
    root_spec = deepcopy(root.get("spec", {}))
    root_spec.pop("syncPolicy", None)
    return {
        "root_uid": root["metadata"]["uid"],
        "root_source_spec": root_spec,
        "namespace_uid": namespace["metadata"]["uid"],
        "namespace_resource_version": namespace["metadata"]["resourceVersion"],
        "namespace_source": deepcopy(source),
        "finished_at": root["status"]["operationState"]["finishedAt"],
        "revisions": deepcopy(
            root["status"]["sync"].get(
                "revisions", [root["status"]["sync"].get("revision", "")]
            )
        ),
        "owned_appset_policy_change": not appset.get("absent")
        and (not appset["present"] or appset["value"] != appset["held_value"]),
    }


def node_operation_bind(snapshot, resource, patch):
    """Bind invariant source bytes separately from the small controlled field."""
    result = deepcopy(snapshot)
    result["source_spec"] = deepcopy(resource.get("spec", {}))
    result["source_spec"].pop(snapshot["field"], None)
    result["held_value"] = next(
        row["value"]
        for row in patch
        if row["op"] == "add" and row["path"] == "/spec/" + snapshot["field"]
    )
    return result


def node_operation_target_valid(snapshot, resources, mode="held", deleting=False):
    if snapshot.get("absent"):
        if resources:
            raise ValueError(
                "previously absent native fence target appeared without ownership"
            )
        return True
    if len(resources) != 1:
        raise ValueError("native fence target disappeared")
    current = resources[0]
    meta = current.get("metadata", {})
    if meta.get("uid") != snapshot["uid"] or not meta.get("resourceVersion"):
        raise ValueError("native fence target identity changed")
    if bool(meta.get("deletionTimestamp")) != deleting:
        raise ValueError("native fence target deletion state is not authorized")
    spec = deepcopy(current.get("spec", {}))
    present = snapshot["field"] in spec
    value = spec.pop(snapshot["field"], None)
    if spec != snapshot["source_spec"]:
        raise ValueError("native fence source changed; retain ownership for inspection")
    original = present == snapshot["present"] and (
        not present or value == snapshot["value"]
    )
    held = present and value == snapshot["held_value"]
    if not (
        held if mode == "held" else original if mode == "original" else original or held
    ):
        raise ValueError("native fence policy changed outside the recorded transaction")
    if snapshot["role"] in {"root", "application"}:
        if current.get("operation") or current.get("status", {}).get(
            "operationState", {}
        ).get("phase") in {"Running", "Terminating"}:
            raise ValueError(
                "foreign queued or running Application operation must remain parked"
            )
        if (
            mode == "held"
            and meta.get("annotations", {}).get("argocd.argoproj.io/skip-reconcile")
            != "true"
        ):
            raise ValueError("native reconciliation skip changed")
    return True


def node_operation_missing_safe(snapshots):
    by_role = {row["role"]: row for row in snapshots}
    # An absent child is allowed only behind an absent or captured parent;
    # the barrier later proves that it remained absent after parent fencing.
    if by_role["application"].get("absent") and not by_role["appset"].get("absent"):
        raise ValueError(
            "a create-only ApplicationSet can still create a missing Tuppr Application"
        )
    if any(row.get("absent") for row in snapshots):
        if not all(
            role in by_role for role in ["root", "appset", "application", "tuppr"]
        ):
            raise ValueError("incomplete native reconciliation inventory")
    return True


def node_operation_deleting_patch(snapshot, current):
    node_operation_target_valid(snapshot, [current], "held", deleting=True)
    path = "/metadata/annotations/argocd.argoproj.io~1skip-reconcile"
    return [
        {"op": "test", "path": "/metadata/uid", "value": snapshot["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": current["metadata"]["resourceVersion"],
        },
        {"op": "remove", "path": path},
    ]


class FilterModule:
    def filters(self):
        return {
            name: value
            for name, value in globals().items()
            if name.startswith("node_operation_") and callable(value)
        }
