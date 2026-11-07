"""Pure cold-bootstrap planning; Kubernetes I/O belongs to kubernetes.core tasks."""

import hashlib
import json
import re
from copy import deepcopy

import yaml

LABEL = "home-ops/cold-recovery"
SKIP = {
    "HTTPRoute",
    "TCPRoute",
    "UDPRoute",
    "GRPCRoute",
    "ReferenceGrant",
    "DNSEndpoint",
}
SAFE = {
    "Namespace",
    "Service",
    "ServiceAccount",
    "Secret",
    "ConfigMap",
    "PersistentVolumeClaim",
    "PersistentVolume",
    "Role",
    "RoleBinding",
    "ClusterRole",
    "ClusterRoleBinding",
    "ExternalSecret",
    "CustomResourceDefinition",
}


class KubernetesLoader(yaml.SafeLoader):
    """Native chart CRDs may contain an unquoted '=' enum/default."""


KubernetesLoader.add_constructor(
    "tag:yaml.org,2002:value", KubernetesLoader.construct_scalar
)


def cold_yaml(value):
    return [r for r in yaml.load_all(value, Loader=KubernetesLoader) if r is not None]


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def identity(resource):
    return {
        "api_version": resource["apiVersion"],
        "kind": resource["kind"],
        "namespace": resource["metadata"].get("namespace", ""),
        "name": resource["metadata"]["name"],
    }


def cold_scope(registry, apps, revision, operation):
    names = {**registry.get("consumers", {}), **registry.get("file_consumers", {})}
    if (
        registry.get("version") != 1
        or not isinstance(apps, list)
        or not apps
        or len(apps) != len(set(apps))
        or set(apps) - names.keys()
    ):
        raise ValueError("cold recovery needs an explicit unique registered scope")
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]{0,51}", operation
    ):
        raise ValueError(
            "cold recovery needs an immutable revision and bounded operation"
        )
    return True


def cold_resources(resources, registry, apps, namespace, name, token):
    names = {**registry.get("consumers", {}), **registry.get("file_consumers", {})}
    consumer = name in names
    expected = {
        (w["kind"], w["name"]) for w in names.get(name, {}).get("workloads", [])
    }
    observed = set()
    output = []
    for raw in resources:
        if not raw:
            continue
        value = deepcopy(raw)
        kind = value["kind"]
        if kind in SKIP:
            continue
        expected_api = (
            "apps/v1"
            if kind in {"Deployment", "StatefulSet"}
            else "batch/v1"
            if kind == "CronJob"
            else "rbac.authorization.k8s.io/v1"
            if kind in {"Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding"}
            else "external-secrets.io/v1"
            if kind == "ExternalSecret"
            else "apiextensions.k8s.io/v1"
            if kind == "CustomResourceDefinition"
            else "v1"
        )
        if value["apiVersion"] != expected_api:
            raise ValueError("unsupported recovery API for resource kind")
        if value.get("metadata", {}).get("annotations", {}).get("helm.sh/hook"):
            raise ValueError("unsupported recovery Helm hook")
        if kind in {"Deployment", "StatefulSet"}:
            key = (kind, value["metadata"]["name"])
            observed.add(key)
            if consumer or name == "tuppr":
                value.setdefault("spec", {})["replicas"] = 0
        elif kind == "CronJob":
            value.setdefault("spec", {})["suspend"] = True
        elif kind not in SAFE:
            raise ValueError("unsupported recovery resource: " + kind)
        if kind not in {
            "Namespace",
            "CustomResourceDefinition",
            "ClusterRole",
            "ClusterRoleBinding",
            "PersistentVolume",
        }:
            value["metadata"].setdefault("namespace", namespace)
        value["metadata"].setdefault("labels", {})[LABEL] = token
        output.append(value)
    if consumer and not expected.issubset(observed):
        raise ValueError("registered controller absent from native Helm render")
    return sorted(
        output,
        key=lambda row: (
            0
            if row["kind"] == "CustomResourceDefinition"
            else 1
            if row["kind"] == "Namespace"
            else 2
            if row["kind"] in SAFE
            else 3
        ),
    )


def cold_consumer_pods(pods, registry):
    names = {**registry.get("consumers", {}), **registry.get("file_consumers", {})}
    result = []
    for pod in pods:
        if pod.get("status", {}).get("phase") in {"Succeeded", "Failed"}:
            continue
        metadata = pod.get("metadata", {})
        for name, consumer in names.items():
            if metadata.get("namespace") != consumer["namespace"]:
                continue
            owners = [metadata.get("name", "")] + [
                o.get("name", "") for o in metadata.get("ownerReferences", [])
            ]
            labels = metadata.get("labels", {})
            workloads = [w["name"] for w in consumer.get("workloads", [])] + [name]
            if labels.get("app.kubernetes.io/instance") == name or any(
                owner == w or owner.startswith(w + "-")
                for owner in owners
                for w in workloads
            ):
                result.append(pod)
                break
    return result


def cold_existing(
    journal, existing, registry, apps, revision, operation, source_sha256
):
    cold_scope(registry, apps, revision, operation)
    if not journal:
        if existing:
            raise ValueError(
                "cold initialization refuses existing consumers or GitOps resources"
            )
        return True
    if any(
        journal.get(k) != v
        for k, v in {
            "version": 1,
            "apps": apps,
            "revision": revision,
            "operation": operation,
            "source_sha256": source_sha256,
        }.items()
    ) or journal.get("phase") not in {
        "initializing",
        "bootstrap-claimed",
        "bootstrap-fencing",
        "bootstrapping",
        "held",
        "restore-complete",
    }:
        raise ValueError(
            "cold retry must preserve exact source, identity, scope and held phase"
        )
    token = journal.get("token")
    for resource in existing:
        if (
            not token
            or resource.get("metadata", {}).get("labels", {}).get(LABEL) != token
        ):
            raise ValueError("cold retry found an unowned existing resource")
        key = identity(resource)
        original = next(
            (
                r
                for r in journal.get("inventory", [])
                if all(r.get(k) == v for k, v in key.items())
            ),
            None,
        )
        if (
            original
            and original.get("uid")
            and original["uid"] != resource["metadata"].get("uid")
        ):
            raise ValueError("cold resource identity changed")
        if (
            resource["kind"] in {"Deployment", "StatefulSet"}
            and resource.get("spec", {}).get("replicas", 1) != 0
        ):
            raise ValueError("cold consumer no longer held")
        if (
            resource["kind"] == "Application"
            and resource.get("spec", {}).get("syncPolicy", {}).get("automated")
            is not None
        ):
            raise ValueError("cold GitOps no longer held")
        if resource["kind"] == "ApplicationSet" and (
            resource.get("spec", {}).get("generators") != [{"list": {"elements": []}}]
            or resource.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("syncPolicy", {})
            .get("automated")
            is not None
        ):
            raise ValueError("cold ApplicationSet no longer held")
    return True


def cold_gitops(root, appset, releases, revision, token):
    root = deepcopy(root)
    root["spec"].pop("syncPolicy", None)
    for source in root["spec"]["sources"]:
        source["targetRevision"] = revision
    root["metadata"].setdefault("labels", {})[LABEL] = token
    root["metadata"].setdefault("annotations", {})[
        "argocd.argoproj.io/skip-reconcile"
    ] = "true"
    appset = deepcopy(appset)
    appset["spec"]["generators"] = [{"list": {"elements": []}}]
    appset["spec"]["syncPolicy"] = {
        "applicationsSync": "create-only",
        "preserveResourcesOnDeletion": True,
    }
    appset["spec"]["template"]["spec"].pop("syncPolicy", None)
    appset["metadata"].setdefault("labels", {})[LABEL] = token
    children = []
    for release in releases:
        path = release["values_file"].removesuffix("/values.yaml")
        path = path[path.index("apps/") :]
        children.append(
            {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "metadata": {
                    "name": release["name"],
                    "namespace": "argocd",
                    "labels": {LABEL: token},
                    "annotations": {"argocd.argoproj.io/skip-reconcile": "true"},
                },
                "spec": {
                    "project": release["namespace"],
                    "destination": {
                        "server": "https://kubernetes.default.svc",
                        "namespace": release["namespace"],
                    },
                    "sources": [
                        {
                            "repoURL": release["chart_repo_url"]
                            or release["chart_ref"]
                            .removeprefix("oci://")
                            .rsplit("/", 1)[0],
                            "chart": release["chart_ref"].rsplit("/", 1)[-1],
                            "targetRevision": release["chart_version"],
                            "helm": {
                                "valueFiles": ["$values/" + path + "/values.yaml"]
                            },
                        },
                        {
                            "repoURL": "https://github.com/edgard/home-ops.git",
                            "targetRevision": revision,
                            "ref": "values",
                        },
                        {
                            "repoURL": "https://github.com/edgard/home-ops.git",
                            "targetRevision": revision,
                            "path": path,
                            "directory": {
                                "recurse": True,
                                "include": "{manifests/*.yaml,manifests/*.yml}",
                            },
                        },
                    ],
                },
            }
        )
    return [root, appset, *children]


def cold_inventory(resources):
    return [{**identity(r), "uid": r["metadata"].get("uid", "")} for r in resources]


def cold_plan_inventory(inventory, definitions):
    output = deepcopy(inventory)
    for row in cold_inventory(definitions):
        if not any(
            all(
                old.get(k) == row[k]
                for k in ("api_version", "kind", "namespace", "name")
            )
            for old in output
        ):
            output.append(row)
    return output


def cold_bound_inventory(journal, reads):
    bound = [r for r in journal.get("inventory", []) if r.get("uid")]
    observed = [resource for read in reads for resource in read.get("resources", [])]
    for row in bound:
        matches = [
            resource
            for resource in observed
            if all(
                identity(resource).get(k) == row[k]
                for k in ("api_version", "kind", "namespace", "name")
            )
        ]
        if len(matches) != 1 or matches[0].get("metadata", {}).get("uid") != row["uid"]:
            raise ValueError(
                "bound recovery resource is missing or its identity changed"
            )
    return True


def cold_journal_patch(journal, uid, version, first=False):
    return [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": version},
        {
            "op": "add",
            "path": "/data" if first else "/data/journal.json",
            "value": {"journal.json": json.dumps(journal)}
            if first
            else json.dumps(journal),
        },
    ]


def cold_bound_apply(definition, resources):
    """An empty UID permits create but rejects adoption through an existing-object patch.

    On retry, the immutable UID and resourceVersion reject replacement/update races
    between the role read and the native module's own read/apply operation.
    """
    value = deepcopy(definition)
    value["metadata"]["uid"] = resources[0]["metadata"]["uid"] if resources else ""
    if resources:
        value["metadata"]["resourceVersion"] = resources[0]["metadata"][
            "resourceVersion"
        ]
    return value


def cold_record(inventory, resource):
    key = identity(resource)
    previous = [r for r in inventory if all(r.get(k) == v for k, v in key.items())]
    if any(
        row.get("uid") and row["uid"] != resource["metadata"].get("uid")
        for row in previous
    ):
        raise ValueError("bound recovery resource identity cannot be replaced")
    return [
        r for r in inventory if any(r.get(k) != v for k, v in key.items())
    ] + cold_inventory([resource])


def cold_normal_bootstrap(journal):
    if not journal:
        return True
    admission = journal.get("admission", {})
    if (
        journal.get("phase") != "admitted"
        or admission.get("global_root_allowed") is not True
        or admission.get("unadmitted_apps") != []
        or admission.get("revision") != journal.get("revision")
        or admission.get("apps") != journal.get("apps")
        or admission.get("cold_token") != journal.get("token")
    ):
        raise ValueError(
            "cold recovery still requires executable validated global admission"
        )
    return True


def cold_admission(journal, receipt, registry=None):
    if registry is None:
        raise ValueError("admission requires the actual bound registry source")
    actual_source = digest({"registry": registry, "revision": journal.get("revision")})
    if (
        journal.get("source_sha256") != actual_source
        or receipt.get("source_sha256") != actual_source
    ):
        raise ValueError("admission registry or receipt source differs from bootstrap")
    tooling = receipt.get("restore_tooling", {})
    if (
        not re.search(r"@sha256:[a-f0-9]{64}$", tooling.get("image", ""))
        or not re.fullmatch(r"[a-f0-9]{40}", tooling.get("image_revision", ""))
        or not tooling.get("pod_uid")
        or tooling.get("code_sha256") != journal.get("executor", {}).get("code_sha256")
        or not re.fullmatch(r"[a-f0-9]{64}", tooling.get("code_sha256", ""))
    ):
        raise ValueError(
            "admission requires separately verified restore image/code provenance"
        )
    recovery = receipt.get("recovery", {})
    if (
        not journal.get("token")
        or receipt.get("cold_token") != journal["token"]
        or receipt.get("apps") != journal["apps"]
        or receipt.get("revision") != journal["revision"]
        or receipt.get("phase") != "complete"
        or receipt.get("operation_kind") != "restore"
    ):
        raise ValueError("admission requires exact completed cold restore evidence")
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", recovery.get(k, "") or "")
        for k in ["selection_sha256", "manifest_sha256"]
    ):
        raise ValueError("admission requires a database-aware immutable manifest")
    native = registry is None or bool(
        set(journal["apps"]) & set(registry.get("consumers", {}))
    )
    redis = registry is None or any(
        registry.get("consumers", {})
        .get(name, {})
        .get("redis", {})
        .get("adopted", True)
        and registry.get("consumers", {}).get(name, {}).get("redis")
        for name in journal["apps"]
    )
    expected = (
        (
            ["provision", "redis-provision"]
            if native
            else ["provision:not-required", "redis-provision:not-required"]
        )
        + ["validate", "postgres", "files"]
        + (["redis"] if redis else ["redis:not-required"])
        + ["validate"]
    )
    if receipt.get("cold_steps") != expected:
        raise ValueError("admission requires every native recovery and validation step")
    return {
        "version": 1,
        "apps": journal["apps"],
        "revision": journal["revision"],
        "cold_token": journal["token"],
        "restore_operation": receipt["operation_id"],
        "source_sha256": actual_source,
        "restore_tooling": deepcopy(tooling),
        "selection_sha256": recovery["selection_sha256"],
        "manifest_sha256": recovery["manifest_sha256"],
        "root_must_resume_last": True,
        "global_root_allowed": bool(registry)
        and set(journal["apps"])
        == set(registry.get("consumers", {})) | set(registry.get("file_consumers", {})),
        "unadmitted_apps": sorted(
            (
                set((registry or {}).get("consumers", {}))
                | set((registry or {}).get("file_consumers", {}))
            )
            - set(journal["apps"])
        ),
    }


class FilterModule:
    def filters(self):
        return {
            "cold_yaml": cold_yaml,
            "cold_digest": digest,
            "cold_identity": identity,
            "cold_scope": cold_scope,
            "cold_resources": cold_resources,
            "cold_existing": cold_existing,
            "cold_consumer_pods": cold_consumer_pods,
            "cold_gitops": cold_gitops,
            "cold_inventory": cold_inventory,
            "cold_admission": cold_admission,
            "cold_normal_bootstrap": cold_normal_bootstrap,
            "cold_record": cold_record,
            "cold_bound_apply": cold_bound_apply,
            "cold_bound_inventory": cold_bound_inventory,
            "cold_plan_inventory": cold_plan_inventory,
            "cold_journal_patch": cold_journal_patch,
        }
