"""Small data and credential guards applied to actual deployment output."""


def check_resources(documents):
    for doc in documents:
        kind, spec = doc.get("kind"), doc.get("spec", {})
        label = f"{kind}/{doc.get('metadata', {}).get('name', 'unnamed')}"
        if kind == "Secret":
            assert not any(
                value
                for field in ("data", "stringData")
                for value in doc.get(field, {}).values()
            ), f"{label}: populated Secret"
        if kind not in {"Deployment", "StatefulSet"}:
            continue
        pod = spec.get("template", {}).get("spec", {})
        claims = [
            volume["persistentVolumeClaim"]
            for volume in pod.get("volumes", [])
            if "persistentVolumeClaim" in volume
        ]
        app_template = (
            doc.get("metadata", {})
            .get("labels", {})
            .get("helm.sh/chart", "")
            .startswith("app-template-")
        )
        if app_template and (claims or spec.get("volumeClaimTemplates")):
            assert spec.get("replicas", 1) == 1, f"{label}: PVC workload replicas"
            if kind == "Deployment":
                assert spec.get("strategy", {}).get("type") == "Recreate", (
                    f"{label}: PVC workload requires Recreate"
                )
        if any(claim.get("claimName") == "media" for claim in claims):
            assert pod.get("securityContext", {}).get("fsGroup") == 0, (
                f"{label}: shared media group"
            )
            assert (
                pod.get("securityContext", {}).get("fsGroupChangePolicy")
                == "OnRootMismatch"
            ), f"{label}: preserve shared media ownership"


def check_paperless(values, documents):
    controllers = values["controllers"]
    main = controllers["main"]["containers"]["app"]["env"]
    gpt = controllers["gpt"]["containers"]["app"]["env"]
    assert gpt.get("PDF_REPLACE", "false") == "false", "Paperless: preserve PDFs"
    assert int(gpt.get("OCR_LIMIT_PAGES", 5)) == 0, "Paperless: complete OCR"
    assert gpt.get("PRESERVE_EXISTING_METADATA") == "true", (
        "Paperless: preserve existing metadata"
    )
    durable = []
    for doc in documents:
        if doc.get("kind") not in {"Deployment", "StatefulSet"}:
            continue
        pod = doc["spec"]["template"]["spec"]
        persistent = {
            volume["name"]
            for volume in pod.get("volumes", [])
            if "persistentVolumeClaim" in volume
        }
        for container in pod.get("containers", []):
            if container.get("image", "").startswith("icereed/paperless-gpt:"):
                identity = pod.get("securityContext", {}) | container.get(
                    "securityContext", {}
                )
                assert identity.get("runAsUser") == int(main["USERMAP_UID"]), (
                    "Paperless: shared data user"
                )
                assert identity.get("runAsGroup") == int(main["USERMAP_GID"]), (
                    "Paperless: shared data group"
                )
                durable.append(
                    {
                        mount["mountPath"]
                        for mount in container.get("volumeMounts", [])
                        if mount["name"] in persistent
                        and not mount.get("readOnly", False)
                    }
                )
    assert (
        len(durable) == 1 and {"/app/config", "/app/prompts", "/app/db"} <= durable[0]
    ), "Paperless: GPT config, prompts and history require writable PVC mounts"


def check_backup_mounts(rendered_apps):
    """A new app PVC needs a read-only source in its namespace's Restic backup."""
    claims = set()
    protected = set()
    for (namespace, _), documents in rendered_apps.items():
        for doc in documents:
            if (
                doc["kind"] == "PersistentVolumeClaim"
                and doc["spec"].get("storageClassName", "zfs-appdata") == "zfs-appdata"
            ):
                claims.add((namespace, doc["metadata"]["name"]))
            if doc["kind"] != "CronJob":
                continue
            pod = doc["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            volumes = {
                v["name"]: v["persistentVolumeClaim"]["claimName"]
                for v in pod.get("volumes", [])
                if "persistentVolumeClaim" in v
            }
            for container in pod["containers"]:
                if not container["image"].startswith("restic/restic:"):
                    continue
                for mount in container.get("volumeMounts", []):
                    name = volumes.get(mount["name"])
                    if (
                        name
                        and mount["mountPath"] == f"/data/appdata/{namespace}/{name}"
                    ):
                        assert mount.get("readOnly") is True, (
                            f"writable backup source: {namespace}/{name}"
                        )
                        protected.add((namespace, name))
    assert claims == protected, (
        f"appdata backup mount mismatch: missing={sorted(claims - protected)}, "
        f"unexpected={sorted(protected - claims)}"
    )
