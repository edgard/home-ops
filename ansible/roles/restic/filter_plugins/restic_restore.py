"""Bind an ordinary restore to live claims and immutable snapshot IDs before writing."""

import re
from datetime import datetime

from ansible.errors import AnsibleFilterError


def select_snapshot(snapshots, requested, root, namespace):
    paths = ([root], [f"{root}/{namespace}"])
    candidates = [s for s in snapshots if s["paths"] in paths]
    if isinstance(requested, dict):
        requested = requested.get(namespace, "")
    if requested != "latest":
        if not isinstance(requested, str) or not re.fullmatch(
            "[0-9a-f]{8,64}", requested
        ):
            raise AnsibleFilterError(f"Supply a snapshot ID for {namespace}")
        candidates = [s for s in candidates if s["id"].startswith(requested)]
        if len(candidates) != 1:
            raise AnsibleFilterError(
                f"Snapshot {requested} does not uniquely cover {namespace}"
            )
    if not candidates:
        raise AnsibleFilterError(f"No appdata snapshot covers {namespace}")
    snapshot = max(
        candidates, key=lambda s: (datetime.fromisoformat(s["time"]), s["id"])
    )
    if not re.fullmatch("[0-9a-f]{64}", snapshot["id"]):
        raise AnsibleFilterError("Invalid snapshot ID in repository")
    return {"id": snapshot["id"], "legacy": snapshot["paths"] == [root]}


def restore_plan(
    applications, pvcs, pvs, workloads, snapshots, requested, root, excluded
):
    claims = {(p["metadata"]["namespace"], p["metadata"]["name"]): p for p in pvcs}
    volumes = {p["metadata"]["name"]: p for p in pvs}
    controllers = {
        (w["kind"], w["metadata"]["namespace"], w["metadata"]["name"]): w
        for w in workloads
    }
    plan = []
    seen = set()
    for app in sorted(applications, key=lambda a: a["metadata"]["name"]):
        name = app["metadata"]["name"]
        namespace = app["spec"]["destination"]["namespace"]
        selected, writers = [], []
        for resource in app.get("status", {}).get("resources", []):
            kind = resource["kind"]
            ns, key = resource.get("namespace") or namespace, resource["name"]
            if kind in ("Deployment", "StatefulSet"):
                w = controllers.get((kind, ns, key))
                if w is None:
                    raise AnsibleFilterError(f"Missing workload {ns}/{key} in {name}")
                writers.append(
                    {
                        "kind": kind,
                        "namespace": ns,
                        "name": key,
                        "replicas": w["spec"].get("replicas", 1),
                    }
                )
            if kind != "PersistentVolumeClaim" or f"{ns}/{key}" in excluded:
                continue
            pvc = claims.get((ns, key))
            if pvc is None:
                raise AnsibleFilterError(f"Missing claim {ns}/{key} in {name}")
            if pvc["spec"].get("storageClassName") != "zfs-appdata":
                continue
            pv = volumes.get(pvc["spec"].get("volumeName"), {})
            spec = pv.get("spec", {})
            ref, csi = spec.get("claimRef", {}), spec.get("csi", {})
            handle = csi.get("volumeHandle", "")
            if (
                ns != namespace
                or (ns, key) in seen
                or pvc["status"]["phase"] != "Bound"
                or (ref.get("namespace"), ref.get("name"), ref.get("uid"))
                != (ns, key, pvc["metadata"]["uid"])
                or pv.get("status", {}).get("phase") != "Bound"
                or spec.get("persistentVolumeReclaimPolicy") != "Retain"
                or spec.get("volumeMode", "Filesystem") != "Filesystem"
                or spec.get("storageClassName") != "zfs-appdata"
                or csi.get("driver") != "zfs.csi.openebs.io"
                or handle != f"pvc-{ref.get('uid')}"
                or not re.fullmatch(r"pvc-[0-9a-f-]{36}", handle)
            ):
                raise AnsibleFilterError(
                    f"Unexpected ownership or OpenEBS binding for {ns}/{key}"
                )
            seen.add((ns, key))
            selected.append(
                {
                    "name": key,
                    "uid": ref["uid"],
                    "dataset": f"dpool/k8s/{handle}",
                    "path": f"{root}/{ns}/{key}",
                }
            )
        if selected:
            snapshot = select_snapshot(snapshots, requested, root, namespace)
            plan.append(
                {
                    "app": name,
                    "namespace": namespace,
                    "claims": selected,
                    "snapshot": snapshot,
                    "workloads": writers,
                }
            )
    return plan


def claim_consumers(resources, plan, field):
    claims = {(a["namespace"], c["name"]) for a in plan for c in a["claims"]}
    consumers = []
    for obj in resources:
        ns = obj["metadata"]["namespace"]
        if field == "cronjob":
            spec = obj["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        else:
            if obj.get("status", {}).get("phase") in ("Succeeded", "Failed"):
                continue
            spec = obj["spec"]
        attached = {
            (ns, v["persistentVolumeClaim"]["claimName"])
            for v in spec.get("volumes", [])
            if "persistentVolumeClaim" in v
        }
        if claims & attached or (
            field == "cronjob"
            and (ns, obj["metadata"]["name"]) == ("selfhosted", "restic-maintenance")
        ):
            consumers.append(
                {
                    "namespace": ns,
                    "name": obj["metadata"]["name"],
                    "suspend": obj["spec"].get("suspend", False),
                }
            )
    return consumers


def unfinished_jobs(jobs, cronjob):
    active = []
    for job in jobs:
        if not any(
            o["kind"] == "CronJob" and o["name"] == cronjob
            for o in job["metadata"].get("ownerReferences", [])
        ):
            continue
        conditions = job.get("status", {}).get("conditions", [])
        if not any(
            c["type"] in ("Complete", "Failed") and c["status"] == "True"
            for c in conditions
        ):
            active.append(job["metadata"]["name"])
    return active


class FilterModule:
    def filters(self):
        return {
            "restic_restore_bindings": restore_plan,
            "restic_claim_consumers": claim_consumers,
            "restic_unfinished_jobs": unfinished_jobs,
        }
