"""Check GitOps storage ownership against Kubernetes and the host's native ZFS inventory."""

import re
from uuid import UUID

from ansible.errors import AnsibleFilterError


def require(condition, message):
    if not condition:
        raise AnsibleFilterError(message)


def guid(value):
    return isinstance(value, str) and value.isdecimal() and 0 < int(value) < 2**64


def claim_key(resource):
    meta = resource["metadata"]
    return f"{meta['namespace']}/{meta['name']}"


def recovery_claims(document, pool_guid, records):
    """Validate automated and operator evidence before rendering any value into a Pod."""
    rows = []
    for record in records:
        data = record["data"]
        require(
            record.get("immutable")
            and not record["metadata"].get("deletionTimestamp")
            and data["verification"] == "restic-verify"
            and data["pool_guid"] == pool_guid
            and re.fullmatch(r"[0-9a-f]{64}", data["restic_snapshot"])
            and record["metadata"]["name"] == "platform-recovery-" + data["uid"]
            and record["metadata"]["namespace"] == data["namespace"],
            "Invalid automatic restore checkpoint",
        )
        rows.append(data)
    if document is not None:
        require(document.get("pool_guid") == pool_guid, "Recovery pool GUID differs")
        manual = document.get("claims")
        require(
            isinstance(manual, list) and manual,
            "Missing operator recovery claim inventory",
        )
        require(
            all(
                r["verification"] in {"retained-checksum", "native-postgresql"}
                for r in manual
            ),
            "Manual evidence requires a verified recovery method for retained data or native PostgreSQL",
        )
        rows.extend(manual)
    require(
        rows,
        "No verified appdata. Complete recovery or explicitly request a first-ever empty site.",
    )
    names, uids = set(), set()
    for row in rows:
        name = f"{row['namespace']}/{row['name']}"
        uid = row["uid"]
        require(
            re.fullmatch(r"[a-z0-9.-]+/[a-z0-9.-]+", name)
            and name not in names
            and uid not in uids
            and str(UUID(uid)) == uid
            and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", row["snapshot"])
            and guid(row["dataset_guid"])
            and guid(row["snapshot_guid"]),
            f"Invalid or duplicate recovery identity for {name}",
        )
        native_db = name == "selfhosted/sparkyfitness-data"
        methods = (
            {"native-postgresql"}
            if native_db
            else {"restic-verify", "retained-checksum"}
        )
        require(
            row["verification"] in methods,
            f"Missing verified recovery method for {name}",
        )
        names.add(name)
        uids.add(uid)
    return rows


def storage_bindings(desired, inventory, dataset_log, recovery, fresh, cluster_uid):
    resources = {r["item"]["kind"]: r["resources"] for r in inventory}
    require(all(r["api_found"] for r in inventory), "Missing Kubernetes or CSI API")
    datasets = {}
    for line in dataset_log.splitlines():
        path, kind, identity = line.split("\t")
        require(guid(identity) and path not in datasets, "Invalid native ZFS inventory")
        datasets[path] = (kind, identity)
    expected = {claim_key(c) for c in desired}
    require(
        expected and len(expected) == len(desired),
        "Missing or duplicated desired claim",
    )
    static = {
        "media/media": "/var/mnt/dpool/media",
        "selfhosted/restic-repo": "/var/mnt/dpool/restic",
    }
    pvcs = {claim_key(r): r for r in resources["PersistentVolumeClaim"]}
    pvs = {r["metadata"]["name"]: r for r in resources["PersistentVolume"]}
    zvols = {r["metadata"]["name"]: r for r in resources["ZFSVolume"]}
    classes = {r["metadata"]["name"]: r for r in resources["StorageClass"]}
    sc = classes.get("zfs-appdata", {})
    default_classes = {
        name
        for name, item in classes.items()
        if item["metadata"]
        .get("annotations", {})
        .get("storageclass.kubernetes.io/is-default-class")
        == "true"
    }
    require(
        default_classes == {"zfs-appdata"}
        and sc.get("provisioner") == "zfs.csi.openebs.io"
        and sc.get("reclaimPolicy") == "Retain"
        and sc.get("volumeBindingMode") == "WaitForFirstConsumer"
        and sc.get("parameters", {}).get("poolname") == "dpool/k8s"
        and sc["parameters"].get("fstype") == "zfs"
        and sc["parameters"].get("shared") == "yes",
        "Unexpected OpenEBS StorageClass",
    )
    managed = {
        k for k, v in pvcs.items() if v["spec"].get("storageClassName") == "zfs-appdata"
    }
    if fresh or recovery:
        require(
            managed == expected,
            "Unexpected or missing appdata claims before first release",
        )
    evidence = {f"{r['namespace']}/{r['name']}": r for r in recovery}
    if recovery:
        require(
            set(evidence) == expected,
            "Supply recovery evidence for every current appdata claim",
        )
    bound = {}
    for key in sorted(expected | managed | set(static)):
        claim = pvcs.get(key, {})
        require(claim.get("status", {}).get("phase") == "Bound", f"Unbound claim {key}")
        meta, spec = claim["metadata"], claim["spec"]
        uid, volume = meta["uid"], spec.get("volumeName")
        pv = pvs.get(volume, {})
        ref = pv.get("spec", {}).get("claimRef", {})
        require(
            str(UUID(uid)) == uid
            and not meta.get("deletionTimestamp")
            and spec.get("accessModes") == ["ReadWriteOnce"]
            and spec.get("volumeMode", "Filesystem") == "Filesystem"
            and pv.get("status", {}).get("phase") == "Bound"
            and not pv["metadata"].get("deletionTimestamp")
            and pv["spec"].get("persistentVolumeReclaimPolicy") == "Retain"
            and pv["spec"].get("accessModes") == ["ReadWriteOnce"]
            and pv["spec"].get("volumeMode", "Filesystem") == "Filesystem"
            and (ref.get("namespace"), ref.get("name"), ref.get("uid"))
            == (meta["namespace"], meta["name"], uid),
            f"Wrong retained binding for {key}",
        )
        selector = "kubernetes.io/hostname" if key in static else "openebs.io/nodeid"
        affinity = (
            pv["spec"]
            .get("nodeAffinity", {})
            .get("required", {})
            .get("nodeSelectorTerms")
        )
        require(
            affinity
            == [
                {
                    "matchExpressions": [
                        {"key": selector, "operator": "In", "values": ["homelab"]}
                    ]
                }
            ],
            f"Wrong volume node affinity for {key}",
        )
        if key in static:
            require(
                not spec.get("storageClassName")
                and not pv["spec"].get("storageClassName")
                and volume == meta["name"]
                and pv["spec"].get("local", {}).get("path") == static[key],
                f"Wrong shared volume for {key}",
            )
            continue
        handle = "pvc-" + uid
        ds = datasets.get("dpool/k8s/" + handle, ("", ""))
        zvol = zvols.get(handle, {})
        csi = pv["spec"].get("csi", {})
        backend = zvol.get("spec", {})
        require(
            spec.get("storageClassName")
            == pv["spec"].get("storageClassName")
            == "zfs-appdata"
            and spec.get("dataSource") is None
            and spec.get("dataSourceRef") is None
            and csi.get("driver") == "zfs.csi.openebs.io"
            and csi.get("fsType") == "zfs"
            and csi.get("volumeHandle") == volume == handle
            and tuple(
                backend.get(k)
                for k in ("ownerNodeID", "poolName", "volumeType", "fsType", "shared")
            )
            == ("homelab", "dpool/k8s", "DATASET", "zfs", "yes")
            and zvol.get("status", {}).get("state") == "Ready"
            and not zvol["metadata"].get("deletionTimestamp")
            and ds[0] == "filesystem",
            f"Wrong CSI volume or native dataset for {key}",
        )
        if fresh:
            require(
                meta.get("annotations", {}).get("home-ops.edgard.org/recovery-claim")
                == cluster_uid,
                f"{key} was not prepared for this Kubernetes installation",
            )
        if recovery:
            require(
                evidence[key]["uid"] == uid and evidence[key]["dataset_guid"] == ds[1],
                f"Recovered handle or dataset changed for {key}",
            )
        bound[key] = uid
    if fresh:
        require(
            set(datasets)
            == {"dpool/k8s"} | {"dpool/k8s/pvc-" + uid for uid in bound.values()},
            "Existing appdata datasets require recovery",
        )
    return bound


def recovery_consumers(results, namespaces):
    offenders = []
    for result in results:
        require(result["api_found"], f"Missing {result['item']['kind']} API")
        for obj in result["resources"]:
            kind, spec, status = obj["kind"], obj.get("spec", {}), obj.get("status", {})
            name = claim_key(obj)
            if kind in ("Application", "ApplicationSet"):
                offenders.append(f"{kind} {name}")
                continue
            app_namespace = obj["metadata"]["namespace"] in namespaces
            if kind == "Job" and any(
                c["type"] in ("Complete", "Failed") and c["status"] == "True"
                for c in status.get("conditions", [])
            ):
                continue
            if kind == "Pod" and status.get("phase") in ("Failed", "Succeeded"):
                continue
            templates = spec.get("volumeClaimTemplates")
            if kind == "CronJob":
                spec = spec["jobTemplate"]["spec"]
            template = obj if kind == "Pod" else spec["template"]
            pod = template["spec"]
            labels = template.get("metadata", {}).get("labels", {})
            private_restic = (
                obj["metadata"]["namespace"] == "selfhosted"
                and kind in ("Pod", "Deployment", "ReplicaSet")
                and labels.get("app.kubernetes.io/instance") == "restic"
                and labels.get("app.kubernetes.io/controller") == "main"
            )
            used = app_namespace and bool(templates)
            for volume in pod.get("volumes", []):
                claim = volume.get("persistentVolumeClaim", {}).get("claimName")
                path = volume.get("hostPath", {}).get("path", "")
                direct_pool_mount = path == "/var/mnt/dpool" or path.startswith(
                    "/var/mnt/dpool/"
                )
                if not (claim and app_namespace) and not direct_pool_mount:
                    continue
                mounts = [
                    m
                    for c in pod.get("initContainers", [])
                    + pod["containers"]
                    + pod.get("ephemeralContainers", [])
                    for m in c.get("volumeMounts", [])
                    if m["name"] == volume["name"]
                ]
                if direct_pool_mount:
                    if any(not m.get("readOnly") for m in mounts):
                        used = True
                elif not (
                    private_restic
                    and claim == "restic-repo"
                    and mounts
                    and all(
                        m["mountPath"] == "/repository" and m.get("readOnly")
                        for m in mounts
                    )
                ):
                    used = True
            if used:
                offenders.append(f"{kind} {name}")
    return offenders


class FilterModule:
    def filters(self):
        return {
            "platform_recovery_claims": recovery_claims,
            "platform_storage_bindings": storage_bindings,
            "platform_recovery_consumers": recovery_consumers,
        }
