"""Pure shared-Lease and real Job/Pod executor contracts for cold bootstrap."""

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone

RECORD = "home-ops/data-coordinator"
CONTEXT_KEYS = (
    "apps",
    "revision",
    "source_sha256",
    "image",
    "code_sha256",
    "bundle_sha256",
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def record(lease):
    try:
        return json.loads(
            lease.get("metadata", {}).get("annotations", {}).get(RECORD, "{}")
        )
    except ValueError, TypeError:
        return {}


def same_context(recorded, expected):
    return all(recorded.get(key) == expected.get(key) for key in CONTEXT_KEYS)


def job_identity(actor):
    if actor.get("kind") == "Job":
        return {key: actor[key] for key in ("uid", "name", "namespace")}
    owners = [o for o in actor.get("owners", []) if o.get("kind") == "Job"]
    if actor.get("kind") != "Pod" or len(owners) != 1:
        raise ValueError("cold executor has no exact real Job owner")
    return {
        "uid": owners[0]["uid"],
        "name": owners[0]["name"],
        "namespace": actor["namespace"],
    }


def cold_dispatch_ownership(lease, journal, context, operation):
    if "home-ops/native-operation" in lease.get("metadata", {}).get("finalizers", []):
        raise ValueError("unresolved native CLI ownership cannot become cold recovery")
    holder = lease.get("spec", {}).get("holderIdentity", "")
    if journal and not journal.get("executor", {}).get("job_uid"):
        raise ValueError(
            "unbound legacy/local cold execution needs an explicit fenced transition"
        )
    if not holder:
        if journal.get("phase") in {
            "bootstrap-claimed",
            "bootstrapping",
            "bootstrap-fencing",
        }:
            raise ValueError(
                "ambiguous unfinished cold executor lost shared Lease ownership"
            )
        return {"expected_identity": "", "requires_fence": False, "actors": []}
    entry = record(lease)
    if (
        entry.get("operation_kind") != "cold-bootstrap"
        or entry.get("operation_id") != operation
        or not same_context(entry.get("context", {}), context)
    ):
        raise ValueError("competing or unbound shared maintenance Lease is held")
    actor = entry.get("actor", {})
    if holder != operation + ":" + actor.get("uid", ""):
        raise ValueError("competing shared Lease executor identity is ambiguous")
    job_identity(actor)
    actors = [actor, *entry.get("fence_actors", [])]
    return {"expected_identity": holder, "requires_fence": True, "actors": actors}


def cold_lease_patch(
    lease,
    expected,
    operation,
    actor,
    context,
    now,
    duration=900,
    fence_actors=None,
    phase="claimed",
):
    if lease.get("spec", {}).get("holderIdentity", "") != expected:
        raise ValueError("shared Lease owner changed")
    if actor.get("kind") not in {"Job", "Pod"} or not all(
        actor.get(k) for k in ("uid", "name", "namespace")
    ):
        raise ValueError("a real Job or bound-token Pod executor is required")
    job_identity(actor)
    stamp = (
        datetime.fromtimestamp(float(now), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
    identity = operation + ":" + actor["uid"]
    spec = {
        **lease.get("spec", {}),
        "holderIdentity": identity,
        "leaseDurationSeconds": int(duration),
        "renewTime": stamp,
        "acquireTime": lease.get("spec", {}).get("acquireTime", stamp),
        "leaseTransitions": int(lease.get("spec", {}).get("leaseTransitions", 0))
        + int(expected != identity),
    }
    entry = {
        "operation_id": operation,
        "operation_kind": "cold-bootstrap",
        "actor": deepcopy(actor),
        "context": deepcopy(context),
        "stage": "journaled",
        "cold_phase": phase,
        "fence_actors": deepcopy(fence_actors or []),
    }
    annotations = {
        **lease.get("metadata", {}).get("annotations", {}),
        RECORD: json.dumps(entry, sort_keys=True),
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
        {"op": "add", "path": "/spec", "value": spec},
        {"op": "add", "path": "/metadata/annotations", "value": annotations},
    ]


def expired(lease, now):
    try:
        spec = lease["spec"]
        return float(now) > datetime.fromisoformat(
            spec["renewTime"].replace("Z", "+00:00")
        ).timestamp() + int(spec["leaseDurationSeconds"])
    except KeyError, TypeError, ValueError:
        return False


def ready_nodes(nodes):
    return bool(nodes) and all(
        any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in node.get("status", {}).get("conditions", [])
        )
        and not any(
            t.get("key")
            in {"node.kubernetes.io/unreachable", "node.kubernetes.io/not-ready"}
            for t in node.get("spec", {}).get("taints", [])
        )
        for node in nodes
    )


def cold_fence_plan(lease, journal, jobs, pods, nodes, now, allow_expired=False):
    entry = record(lease)
    if entry.get("operation_kind") != "cold-bootstrap":
        raise ValueError("only exact cold executors may be fenced here")
    actors = [entry["actor"], *entry.get("fence_actors", [])]
    identities = {item["uid"]: item for item in map(job_identity, actors)}
    if any(
        actor.get("kind") == "Pod" and not actor.get("fence_nodes") for actor in actors
    ):
        raise ValueError("old Pod executor lacks durable original node identity")
    selected_jobs = []
    for identity in identities.values():
        matches = [
            j
            for j in jobs
            if j.get("metadata", {}).get("name") == identity["name"]
            and j.get("metadata", {}).get("namespace") == identity["namespace"]
        ]
        if any(j["metadata"]["uid"] != identity["uid"] for j in matches):
            raise ValueError("old executor Job identity changed")
        selected_jobs += matches
    selected_pods = [
        p
        for p in pods
        if p.get("metadata", {}).get("labels", {}).get("home-ops/cold-job-uid")
        in identities
        or any(
            o.get("kind") == "Job" and o.get("uid") in identities
            for o in p.get("metadata", {}).get("ownerReferences", [])
        )
    ]
    terminal = all(
        not j.get("status", {}).get("active")
        and not j.get("status", {}).get("terminating")
        and (
            j.get("status", {}).get("succeeded", 0)
            or j.get("status", {}).get("failed", 0)
        )
        for j in selected_jobs
    ) and all(
        p.get("status", {}).get("phase") in {"Succeeded", "Failed"}
        for p in selected_pods
    )
    if not terminal and not (allow_expired and expired(lease, now)):
        raise ValueError("active old executor requires explicit expired-owner fencing")
    if not ready_nodes(nodes):
        raise ValueError("Ready node evidence is required before executor fencing")
    nodes_by_name = {node["metadata"]["name"]: node for node in nodes}
    required = {
        row["name"]: row["uid"]
        for actor in actors
        for row in actor.get("fence_nodes", [])
    }
    for pod in selected_pods:
        name = pod.get("spec", {}).get("nodeName")
        if not name and pod.get("status", {}).get("phase") != "Pending":
            raise ValueError("old executor has no provable assigned Ready node")
        if name:
            if name not in nodes_by_name or not nodes_by_name[name]["metadata"].get(
                "uid"
            ):
                raise ValueError("old executor node is absent or ambiguous")
            observed_uid = nodes_by_name[name]["metadata"]["uid"]
            if name in required and required[name] != observed_uid:
                raise ValueError("historical fence node identity changed")
            required[name] = observed_uid
    if any(
        name not in nodes_by_name or nodes_by_name[name]["metadata"].get("uid") != uid
        for name, uid in required.items()
    ):
        raise ValueError("historical fence node identity changed or disappeared")
    node_bindings = [
        {"name": name, "uid": uid} for name, uid in sorted(required.items())
    ]
    actors = [{**actor, "fence_nodes": node_bindings} for actor in actors]
    return {
        "actors": actors,
        "jobs": selected_jobs,
        "pods": selected_pods,
        "job_uids": sorted(identities),
        "nodes": node_bindings,
    }


def cold_fenced(plan, jobs, pods, nodes):
    if not ready_nodes(nodes):
        raise ValueError("Ready node evidence is required after executor fencing")
    current_nodes = {node["metadata"]["name"]: node for node in nodes}
    if any(
        row["name"] not in current_nodes
        or current_nodes[row["name"]]["metadata"].get("uid") != row["uid"]
        for row in plan.get("nodes", [])
    ):
        raise ValueError("old executor node identity changed before fencing proof")
    if any(j.get("metadata", {}).get("uid") in plan["job_uids"] for j in jobs) or any(
        any(
            o.get("uid") in plan["job_uids"]
            for o in p.get("metadata", {}).get("ownerReferences", [])
        )
        or p.get("metadata", {}).get("labels", {}).get("home-ops/cold-job-uid")
        in plan["job_uids"]
        for p in pods
    ):
        raise ValueError("old executor or owner can still run/recreate work")
    return True


def cold_worker_proof(job, pod, sa, ssr, journal, lease, context):
    if journal.get("phase") not in {"bootstrap-claimed", "bootstrapping", "held"}:
        raise ValueError(
            "cold worker cannot mutate during unfenced or ambiguous initialization"
        )
    meta = pod.get("metadata", {})
    user = ssr.get("status", {}).get("userInfo", {})
    if user.get("extra", {}).get("authentication.kubernetes.io/pod-uid") != [
        meta.get("uid")
    ]:
        raise ValueError(
            "API-authenticated bound Pod token is required; local/placeholder identity refused"
        )
    sa_meta = sa.get("metadata", {})
    if user.get("uid") != sa_meta.get("uid") or user.get(
        "username"
    ) != "system:serviceaccount:" + sa_meta.get("namespace", "") + ":" + sa_meta.get(
        "name", ""
    ):
        raise ValueError("authenticated ServiceAccount identity differs")
    execution = journal.get("executor", {})
    if execution.get("pod_uid") and execution["pod_uid"] != meta.get("uid"):
        raise ValueError("durably bound worker Pod identity changed")
    owners = meta.get("ownerReferences", [])
    if (
        len(owners) != 1
        or owners[0].get("kind") != "Job"
        or owners[0].get("uid") != job.get("metadata", {}).get("uid")
        or owners[0].get("controller") is not True
        or job.get("metadata", {}).get("uid") != execution.get("job_uid")
        or job.get("metadata", {}).get("name") != execution.get("job_name")
    ):
        raise ValueError("actual Pod/Job owner chain differs from durable executor")
    if (
        meta.get("namespace") != execution.get("namespace")
        or meta.get("deletionTimestamp")
        or pod.get("status", {}).get("phase") != "Running"
        or job.get("spec", {}).get("suspend")
    ):
        raise ValueError("cold executor is not a live unsuspended Job worker")
    spec = job.get("spec", {}).get("template", {}).get("spec", {})
    if (
        digest(spec) != execution.get("job_template_sha256")
        or pod.get("spec", {}).get("serviceAccountName") != sa_meta.get("name")
        or spec.get("serviceAccountName") != sa_meta.get("name")
    ):
        raise ValueError("immutable Job template or ServiceAccount differs")
    for actual in (spec, pod.get("spec", {})):
        containers = actual.get("containers", [])
        if (
            len(containers) != 1
            or containers[0].get("name") != "bootstrap"
            or containers[0].get("image") != context.get("image")
            or actual.get("initContainers")
            or actual.get("ephemeralContainers")
            or any(v.get("hostPath") for v in actual.get("volumes", []))
        ):
            raise ValueError("actual immutable executor image/spec differs")
    entry = record(lease)
    if (
        not same_context(entry.get("context", {}), context)
        or any(
            execution.get(k) != context.get(k)
            for k in ("image", "code_sha256", "bundle_sha256")
        )
        or journal.get("source_sha256") != context.get("source_sha256")
    ):
        raise ValueError("image code or bundled source registry binding differs")
    actor = entry.get("actor", {})
    expected = job["metadata"]["uid"] if actor.get("kind") == "Job" else meta["uid"]
    if (
        entry.get("operation_kind") != "cold-bootstrap"
        or lease.get("spec", {}).get("holderIdentity")
        != journal.get("operation", "") + ":" + expected
        or actor.get("uid") != expected
        or job_identity(actor)["uid"] != job["metadata"]["uid"]
    ):
        raise ValueError("shared Lease and durable executor disagree")
    return True


def cold_worker_actor(pod, node, ssr):
    meta = pod["metadata"]
    node_meta = node.get("metadata", {})
    extra = ssr.get("status", {}).get("userInfo", {}).get("extra", {})
    if not isinstance(extra, dict):
        raise ValueError("API-authenticated original node claims are required")
    claims = {}
    for key in ("node-name", "node-uid"):
        values = extra.get("authentication.kubernetes.io/" + key)
        if (
            not isinstance(values, list)
            or len(values) != 1
            or not isinstance(values[0], str)
            or not values[0].strip()
        ):
            raise ValueError(
                "nonempty unambiguous API-authenticated original node claims are required"
            )
        claims[key] = values[0]
    if (
        not ready_nodes([node])
        or not node_meta.get("uid")
        or claims["node-name"] != pod.get("spec", {}).get("nodeName")
        or claims["node-name"] != node_meta.get("name")
        or claims["node-uid"] != node_meta["uid"]
    ):
        raise ValueError(
            "API-authenticated original node differs from the assigned Ready node"
        )
    return {
        "kind": "Pod",
        "uid": meta["uid"],
        "name": meta["name"],
        "namespace": meta["namespace"],
        "owners": deepcopy(meta["ownerReferences"]),
        "fence_nodes": [{"name": claims["node-name"], "uid": claims["node-uid"]}],
    }


def cold_dispatch_guard(lease, journal, job_uid, context, operation):
    entry = record(lease)
    if (
        lease.get("spec", {}).get("holderIdentity") != operation + ":" + job_uid
        or entry.get("actor", {}).get("kind") != "Job"
        or not same_context(entry.get("context", {}), context)
    ):
        raise ValueError(
            "dispatcher lost its exact shared Lease before executor control"
        )
    if journal and journal.get("executor", {}).get("job_uid") != job_uid:
        raise ValueError("dispatcher and durable executor journal disagree")
    return True


def cold_upgrades_idle(resources, jobs, pods, tuppr):
    if resources or any(row.get("spec", {}).get("replicas", 1) != 0 for row in tuppr):
        raise ValueError(
            "upgrade requests or a running Tuppr controller are incompatible with cold initialization"
        )
    for row in [*jobs, *pods]:
        meta = row.get("metadata", {})
        labels = meta.get("labels", {})
        upgrade = (
            labels.get("app.kubernetes.io/part-of") == "tuppr"
            or labels.get("app.kubernetes.io/name")
            in {"tuppr", "talos-upgrade", "kubernetes-upgrade", "talos-upgrade-hook"}
            or any(
                owner.get("apiVersion", "").startswith("tuppr.home-operations.com/")
                for owner in meta.get("ownerReferences", [])
            )
        )
        if upgrade and row.get("status", {}).get("phase") not in {
            "Succeeded",
            "Failed",
        }:
            raise ValueError("an upgrade worker can still mutate the node")
    return True


def cold_executor_terminal(pods, job_uid, nodes):
    if not ready_nodes(nodes):
        raise ValueError("Ready nodes are required before terminal executor cleanup")
    selected = [
        pod
        for pod in pods
        if any(
            owner.get("uid") == job_uid
            for owner in pod.get("metadata", {}).get("ownerReferences", [])
        )
    ]
    if not selected or any(
        pod.get("status", {}).get("phase") not in {"Succeeded", "Failed"}
        or pod.get("metadata", {}).get("deletionTimestamp")
        for pod in selected
    ):
        raise ValueError("executor Pods are not all proven terminal")
    return True


def cold_lease_release(lease, operation, actor_uid):
    identity = operation + ":" + actor_uid
    if (
        lease.get("spec", {}).get("holderIdentity") != identity
        or record(lease).get("operation_kind") != "cold-bootstrap"
    ):
        raise ValueError(
            "only the exact completed cold executor may release its shared Lease"
        )
    return [
        {"op": "test", "path": "/metadata/uid", "value": lease["metadata"]["uid"]},
        {
            "op": "test",
            "path": "/metadata/resourceVersion",
            "value": lease["metadata"]["resourceVersion"],
        },
        {"op": "test", "path": "/spec/holderIdentity", "value": identity},
        {"op": "add", "path": "/spec/holderIdentity", "value": ""},
    ]


class FilterModule:
    def filters(self):
        return {
            "cold_dispatch_ownership": cold_dispatch_ownership,
            "cold_lease_patch": cold_lease_patch,
            "cold_fence_plan": cold_fence_plan,
            "cold_fenced": cold_fenced,
            "cold_worker_proof": cold_worker_proof,
            "cold_worker_actor": cold_worker_actor,
            "cold_dispatch_guard": cold_dispatch_guard,
            "cold_lease_release": cold_lease_release,
            "cold_executor_terminal": cold_executor_terminal,
            "cold_upgrades_idle": cold_upgrades_idle,
        }
