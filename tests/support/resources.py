"""Guard raw and rendered resource semantics without a policy engine."""

import json
import re

ROOT_IMAGES = (
    "ghcr.io/home-assistant/home-assistant:",
    "ghcr.io/koush/scrypted:",
    "ghcr.io/karakeep-app/karakeep:",
    "ghcr.io/paperless-ngx/paperless-ngx:",
    "icereed/paperless-gpt:",
    "qmcgaw/gluetun:",
    "restic/rest-server:",
    "restic/restic:",
    "ghcr.io/tailscale/tailscale:",
    "lscr.io/linuxserver/",
)
SECURITY_EXCEPTIONS = (
    "docker.io/apache/tika:",
    "docker.io/gotenberg/gotenberg:",
    "docker.io/library/redis:",
    *(image for image in ROOT_IMAGES[:-1] if image != "ghcr.io/karakeep-app/karakeep:"),
)
RETIRED_GROUPS = {"monitoring.coreos.com", "operator.victoriametrics.com"}
RETIRED_WORKLOADS = (
    "alertmanager-kube-prometheus-stack-alertmanager",
    "alloy",
    "gatus-sidecar",
    "kube-prometheus-stack-grafana",
    "loki",
    "prometheus-blackbox-exporter",
    "prometheus-kube-prometheus-stack-prometheus",
    "victoria-logs-",
    "victoria-metrics-k8s-stack-",
    "vmagent-victoria-metrics-k8s-stack",
    "vmsingle-victoria-metrics-k8s-stack",
)


def pod_spec(doc):
    kind, spec = doc["kind"], doc.get("spec", {})
    if kind == "Pod":
        return spec
    if kind in {"Deployment", "StatefulSet", "DaemonSet", "Job"}:
        return spec.get("template", {}).get("spec", {})
    if kind == "CronJob":
        return (
            spec.get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
        )
    return {}


def assert_resource(doc):
    assert isinstance(doc, dict), "resource document"
    kind, meta = doc["kind"], doc["metadata"]
    name, namespace = meta["name"], meta.get("namespace", "")
    label = f"{kind}/{namespace}/{name}"
    annotations = meta.get("annotations", {})
    assert not any(
        key.startswith("external-dns.alpha.kubernetes.io/") for key in annotations
    ), f"retired ExternalDNS annotation: {label}"
    assert "gatus.home-operations.com/endpoint" not in annotations, (
        f"explicit Gatus monitoring: {label}"
    )
    assert doc["apiVersion"].split("/")[0] not in RETIRED_GROUPS, (
        f"retired observability API: {label}"
    )
    if kind == "CustomResourceDefinition":
        assert doc["spec"]["group"] not in RETIRED_GROUPS, (
            f"retired observability CRD: {label}"
        )
    if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
        assert not name.startswith(RETIRED_WORKLOADS), (
            f"retired observability workload: {label}"
        )
    if kind == "Secret":
        assert not any(
            value
            for field in ("data", "stringData")
            for value in doc.get(field, {}).values()
        ), f"populated Secret: {label}"
    if kind == "ExternalSecret":
        assert doc["spec"]["secretStoreRef"]["name"] == "external-secrets-store", (
            f"canonical secret store: {label}"
        )
        assert doc["spec"]["secretStoreRef"]["kind"] == "ClusterSecretStore", (
            f"cluster secret store: {label}"
        )
    if kind == "ClusterSecretStore" and name == "external-secrets-store":
        conditions = doc["spec"]["conditions"]
        assert len(conditions) == 1 and set(conditions[0]) == {"namespaces"}, (
            "restricted secret consumers"
        )
        assert set(conditions[0]["namespaces"]) == {
            "argocd",
            "media",
            "platform-system",
            "selfhosted",
        }, "secret consumer namespaces"
    if kind == "PersistentVolumeClaim":
        assert doc["spec"].get("storageClassName", "") in {
            "",
            "nfs-fast",
            "nfs-media",
            "nfs-restic",
        }, f"approved storage: {label}"
    if kind == "HTTPRoute":
        assert all(
            host.endswith(".edgard.org") for host in doc["spec"].get("hostnames", [])
        ), f"route domain: {label}"
        assert any(
            ref.get("name") == "gateway"
            and ref.get("namespace") == "platform-system"
            and ref.get("sectionName") == "https"
            for ref in doc["spec"].get("parentRefs", [])
        ), f"route gateway: {label}"
    if kind == "Gateway" and name == "gateway" and namespace == "platform-system":
        assert annotations.get("external-dns.kubernetes.io/target"), (
            "gateway DNS target"
        )
    if kind == "ValidatingWebhookConfiguration" and name in {
        "istiod-default-validator",
        "istio-validator-platform-system",
    }:
        assert all(
            webhook.get("failurePolicy", "Fail") == "Fail"
            for webhook in doc["webhooks"]
        ), "fail-closed mesh webhooks"
    if (
        kind == "ConfigMap"
        and name == "values"
        and namespace == "platform-system"
        and meta.get("labels", {}).get("app.kubernetes.io/name") == "istiod"
    ):
        merged = json.loads(doc["data"]["merged-values"])
        assert (
            merged.get("telemetry", {})
            .get("v2", {})
            .get("prometheus", {})
            .get("enabled", True)
            is False
        ), "unused Istio telemetry"
    pod = pod_spec(doc)
    containers = pod.get("containers", []) + pod.get("initContainers", [])
    for container in containers:
        assert not container.get("image", "").lower().endswith(":latest"), (
            f"latest image: {label}"
        )
    if kind == "Deployment" and name == "csi-nfs-controller":
        assert all(
            container["name"] != "csi-snapshotter" for container in containers
        ), "snapshot CRDs required"
    if (
        kind == "Deployment"
        and name == "cert-manager"
        and namespace == "platform-system"
    ):
        for container in containers:
            if container["name"] == "cert-manager-controller":
                assert any(
                    re.fullmatch(
                        r"--metrics-listen-address=(127\.0\.0\.1|localhost|\[::1\]):[0-9]+",
                        arg,
                    )
                    for arg in container.get("args", [])
                ), "local-only unused metrics"
    if kind not in {"Deployment", "StatefulSet"} or not meta.get("labels", {}).get(
        "helm.sh/chart", ""
    ).startswith("app-template-"):
        return
    assert doc["spec"].get("replicas", 1) == 1, f"single replica: {label}"
    if kind == "Deployment":
        assert doc["spec"].get("strategy", {}).get("type") == "Recreate", (
            f"Recreate strategy: {label}"
        )
    pod_security = pod.get("securityContext", {})
    if any(
        volume.get("persistentVolumeClaim", {}).get("claimName") == "media"
        for volume in pod.get("volumes", [])
    ):
        assert pod_security.get("fsGroup") == 0, f"shared media group: {label}"
    for container in containers:
        image = container.get("image", "")
        security = container.get("securityContext", {})
        capabilities = security.get("capabilities", {})
        if not image.startswith(SECURITY_EXCEPTIONS):
            assert not security.get("allowPrivilegeEscalation", False), (
                f"privilege escalation: {label}/{container['name']}"
            )
            assert "ALL" in capabilities.get("drop", []), (
                f"drop capabilities: {label}/{container['name']}"
            )
        if not image.startswith(ROOT_IMAGES):
            assert security.get(
                "runAsNonRoot", pod_security.get("runAsNonRoot", False)
            ), f"non-root: {label}/{container['name']}"
        if image.startswith(
            ("icereed/paperless-gpt:", "ghcr.io/karakeep-app/karakeep:")
        ):
            assert {"CHOWN", "SETUID", "SETGID"} <= set(capabilities.get("add", [])), (
                "s6 entrypoint capabilities"
            )
        if image.startswith("qmcgaw/gluetun:"):
            assert container.get("livenessProbe", {}).get("httpGet") is not None, (
                "VPN HTTP health probe"
            )


def assert_route_coverage(routes, excluded, actual):
    assert all(
        isinstance(hosts, list)
        and all(isinstance(host, str) and host for host in hosts)
        for hosts in (routes, excluded, actual)
    ), "nonempty hostname arrays"
    assert len(actual) == len(set(actual)), "duplicate Gatus HTTP targets"
    expected = set(routes) - set(excluded)
    assert expected == set(actual), (
        f"Gatus coverage: missing={expected - set(actual)}, obsolete={set(actual) - expected}"
    )
