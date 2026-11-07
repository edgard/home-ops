import copy

import jsonpatch
import pytest

from tests.support.resources import assert_resource, assert_route_coverage
from tests.support.runtime import ROOT
from tests.support.sources import manifest_paths, read_yaml

RAW = [
    (path, doc)
    for path in manifest_paths(ROOT)
    for doc in read_yaml(path, multiple=True)
]


@pytest.mark.parametrize(
    "path,doc",
    RAW,
    ids=[
        str(path.relative_to(ROOT))
        + ":"
        + str(doc.get("metadata", {}).get("name", "document"))
        for path, doc in RAW
    ],
)
def test_raw_resources(path, doc):
    assert_resource(doc)


@pytest.fixture
def workload():
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "demo", "labels": {"helm.sh/chart": "app-template-5.1.0"}},
        "spec": {
            "replicas": 1,
            "strategy": {"type": "Recreate"},
            "template": {
                "spec": {
                    "securityContext": {"runAsNonRoot": True},
                    "containers": [
                        {
                            "name": "app",
                            "image": "example/app:v1.2.3",
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                }
            },
        },
    }


@pytest.mark.parametrize(
    "path,value",
    [
        ("/spec/replicas", 2),
        ("/spec/strategy/type", "RollingUpdate"),
        (
            "/spec/template/spec/containers/0/securityContext/allowPrivilegeEscalation",
            True,
        ),
        (
            "/spec/template/spec/containers/0/securityContext/capabilities/drop",
            ["NET_BIND_SERVICE"],
        ),
        ("/spec/template/spec/securityContext/runAsNonRoot", False),
        ("/spec/template/spec/containers/0/image", "example/app:latest"),
    ],
)
def test_workload_security_regressions(workload, path, value):
    assert_resource(workload)
    with pytest.raises(AssertionError):
        assert_resource(
            jsonpatch.apply_patch(
                workload, [{"op": "replace", "path": path, "value": value}]
            )
        )


@pytest.mark.parametrize(
    "actual",
    [
        ["other.edgard.org"],
        ["demo.edgard.org", "obsolete.edgard.org"],
        ["demo.edgard.org", "demo.edgard.org"],
    ],
)
def test_route_coverage_rejects_missing_obsolete_and_duplicate_targets(actual):
    with pytest.raises(AssertionError):
        assert_route_coverage(
            ["demo.edgard.org", "status.edgard.org"], ["status.edgard.org"], actual
        )


def test_route_coverage_deduplicates_raw_and_rendered_hosts():
    assert_route_coverage(
        ["demo.edgard.org", "demo.edgard.org", "status.edgard.org"],
        ["status.edgard.org"],
        ["demo.edgard.org"],
    )


@pytest.mark.parametrize(
    "kind,spec,metadata",
    [
        ("Secret", {}, {"name": "demo"}),
        ("PersistentVolumeClaim", {"storageClassName": "nfs-fast"}, {"name": "demo"}),
        (
            "ExternalSecret",
            {
                "secretStoreRef": {
                    "name": "external-secrets-store",
                    "kind": "ClusterSecretStore",
                }
            },
            {"name": "demo"},
        ),
        (
            "ClusterSecretStore",
            {
                "conditions": [
                    {"namespaces": ["argocd", "media", "platform-system", "selfhosted"]}
                ]
            },
            {"name": "external-secrets-store"},
        ),
        (
            "HTTPRoute",
            {
                "hostnames": ["demo.edgard.org"],
                "parentRefs": [
                    {
                        "name": "gateway",
                        "namespace": "platform-system",
                        "sectionName": "https",
                    }
                ],
            },
            {"name": "demo"},
        ),
        (
            "Gateway",
            {},
            {
                "name": "gateway",
                "namespace": "platform-system",
                "annotations": {"external-dns.kubernetes.io/target": "192.0.2.1"},
            },
        ),
    ],
)
def test_resource_hygiene_valid_and_invalid(kind, spec, metadata):
    resource = {"apiVersion": "v1", "kind": kind, "metadata": metadata, "spec": spec}
    assert_resource(resource)
    mutations = {
        "Secret": [
            ("/data", {"token": "synthetic"}),
            ("/stringData", {"token": "synthetic"}),
        ],
        "PersistentVolumeClaim": [("/spec/storageClassName", "local-path")],
        "ExternalSecret": [
            ("/spec/secretStoreRef/name", "other"),
            ("/spec/secretStoreRef/kind", "SecretStore"),
        ],
        "ClusterSecretStore": [
            ("/spec/conditions", []),
            ("/spec/conditions", [{"namespaces": ["argocd"]}]),
            ("/spec/conditions", [{"namespaceSelector": {}}]),
        ],
        "HTTPRoute": [
            ("/spec/hostnames", ["outside.example"]),
            ("/spec/parentRefs", []),
            (
                "/spec/parentRefs",
                [{"name": "gateway", "namespace": "wrong", "sectionName": "https"}],
            ),
        ],
        "Gateway": [("/metadata/annotations", {})],
    }
    for path, value in mutations[kind]:
        with pytest.raises(AssertionError):
            assert_resource(
                jsonpatch.apply_patch(
                    resource, [{"op": "add", "path": path, "value": value}]
                )
            )
    for annotation in [
        "external-dns.alpha.kubernetes.io/target",
        "gatus.home-operations.com/endpoint",
    ]:
        bad = copy.deepcopy(resource)
        bad["metadata"]["annotations"] = {annotation: "synthetic"}
        with pytest.raises(AssertionError):
            assert_resource(bad)


@pytest.mark.parametrize(
    "kind", ["Deployment", "StatefulSet", "DaemonSet", "Pod", "Job", "CronJob"]
)
def test_latest_images_in_every_pod_location(workload, kind):
    resource = copy.deepcopy(workload)
    resource["kind"] = kind
    resource["metadata"]["labels"] = {}
    pod = resource["spec"]["template"]["spec"]
    if kind == "Pod":
        resource["spec"] = pod
    if kind == "CronJob":
        resource["spec"] = {"jobTemplate": {"spec": {"template": {"spec": pod}}}}
    for field in ["containers", "initContainers"]:
        pod[field] = [{"name": "app", "image": "example/app:latest"}]
        with pytest.raises(AssertionError):
            assert_resource(resource)
        pod[field][0]["image"] = "example/app:v1.0.0"
        assert_resource(resource)


@pytest.mark.parametrize("field", ["containers", "initContainers"])
def test_effective_security_context_and_exceptions(workload, field):
    pod = workload["spec"]["template"]["spec"]
    container = copy.deepcopy(pod["containers"][0])
    pod["containers"] = []
    pod[field] = [container]
    container["securityContext"]["runAsNonRoot"] = False
    with pytest.raises(AssertionError):
        assert_resource(workload)
    del container["securityContext"]["runAsNonRoot"]
    assert_resource(workload)
    container["image"] = "lscr.io/linuxserver/demo:1.0"
    pod["securityContext"]["runAsNonRoot"] = False
    assert_resource(workload)
    container["securityContext"]["allowPrivilegeEscalation"] = True
    with pytest.raises(AssertionError):
        assert_resource(workload)
    container["image"] = "restic/restic:1.0"
    assert_resource(workload)
    container["image"] = "ghcr.io/karakeep-app/karakeep:1.0"
    with pytest.raises(AssertionError):
        assert_resource(workload)


@pytest.mark.parametrize(
    "image",
    ["ghcr.io/karakeep-app/karakeep:0.34.1", "icereed/paperless-gpt:1.0"],
)
def test_s6_entrypoint_capabilities(workload, image):
    container = workload["spec"]["template"]["spec"]["containers"][0]
    container["image"] = image
    capabilities = container["securityContext"]["capabilities"]
    required = {"CHOWN", "SETUID", "SETGID"}
    capabilities["add"] = sorted(required)
    assert_resource(workload)
    for missing in required:
        capabilities["add"] = sorted(required - {missing})
        with pytest.raises(AssertionError, match="entrypoint capabilities"):
            assert_resource(workload)


def test_specific_runtime_and_observability_guards(workload):
    pod = workload["spec"]["template"]["spec"]
    pod["volumes"] = [{"persistentVolumeClaim": {"claimName": "media"}}]
    with pytest.raises(AssertionError):
        assert_resource(workload)
    pod["securityContext"]["fsGroup"] = 0
    assert_resource(workload)
    container = pod["containers"][0]
    container["image"] = "icereed/paperless-gpt:1.0"
    with pytest.raises(AssertionError):
        assert_resource(workload)
    container["securityContext"]["capabilities"]["add"] = ["CHOWN", "SETUID", "SETGID"]
    assert_resource(workload)
    container["image"] = "qmcgaw/gluetun:1.0"
    with pytest.raises(AssertionError):
        assert_resource(workload)
    container["livenessProbe"] = {"httpGet": {"port": 9999}}
    assert_resource(workload)
    workload["metadata"]["labels"] = {}
    workload["metadata"]["name"] = "csi-nfs-controller"
    container["name"] = "csi-snapshotter"
    with pytest.raises(AssertionError):
        assert_resource(workload)
    container["name"] = "cert-manager-controller"
    workload["metadata"].update(name="cert-manager", namespace="platform-system")
    with pytest.raises(AssertionError):
        assert_resource(workload)
    for address in ["127.0.0.1", "localhost", "[::1]"]:
        container["args"] = ["--metrics-listen-address=" + address + ":9402"]
        assert_resource(workload)
    container["args"] = ["--metrics-listen-address=0.0.0.0:9402"]
    with pytest.raises(AssertionError):
        assert_resource(workload)
    from tests.support.resources import RETIRED_GROUPS, RETIRED_WORKLOADS

    for name in RETIRED_WORKLOADS:
        workload["metadata"]["name"] = name + "-synthetic"
        with pytest.raises(AssertionError):
            assert_resource(workload)
    for group in RETIRED_GROUPS:
        with pytest.raises(AssertionError):
            assert_resource(
                {
                    "apiVersion": group + "/v1",
                    "kind": "ServiceMonitor",
                    "metadata": {"name": "demo"},
                }
            )
        with pytest.raises(AssertionError):
            assert_resource(
                {
                    "apiVersion": "apiextensions.k8s.io/v1",
                    "kind": "CustomResourceDefinition",
                    "metadata": {"name": "demo"},
                    "spec": {"group": group},
                }
            )
    for name in ["istiod-default-validator", "istio-validator-platform-system"]:
        resource = {
            "apiVersion": "admissionregistration.k8s.io/v1",
            "kind": "ValidatingWebhookConfiguration",
            "metadata": {"name": name},
            "webhooks": [{}],
        }
        assert_resource(resource)
        resource["webhooks"][0]["failurePolicy"] = "Ignore"
        with pytest.raises(AssertionError):
            assert_resource(resource)
    import json

    resource = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": "values",
            "namespace": "platform-system",
            "labels": {"app.kubernetes.io/name": "istiod"},
        },
        "data": {
            "merged-values": json.dumps(
                {"telemetry": {"v2": {"prometheus": {"enabled": False}}}}
            )
        },
    }
    assert_resource(resource)
    resource["data"]["merged-values"] = "{}"
    with pytest.raises(AssertionError):
        assert_resource(resource)
