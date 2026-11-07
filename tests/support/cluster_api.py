"""Local Kubernetes HTTP fixture; synthetic values only, never a cluster client."""

import base64
import copy
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import TCPServer
from urllib.parse import parse_qs, urlsplit

import jsonpatch

root = Path(sys.argv[1])


def state():
    return json.loads((root / "api-state.json").read_text())


def save(value):
    (root / "api-state.json").write_text(json.dumps(value))


def advance_native_lifecycle(current):
    """Model only real controller boundaries: skip stalls Application finalizers."""
    if not current.get("model_root_cascade"):
        return
    objects = current["objects"]
    root_key = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
    app_key = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/tuppr"
    appset_key = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applicationsets/apps"
    deployment_key = "/apis/apps/v1/namespaces/platform-system/deployments/tuppr"
    root_app = objects.get(root_key)
    if not root_app:
        return

    def skipped(value):
        return (
            value.get("metadata", {})
            .get("annotations", {})
            .get("argocd.argoproj.io/skip-reconcile")
            == "true"
        )

    if root_app["metadata"].get("deletionTimestamp"):
        if skipped(root_app):
            current["root_finalizer_stalled_on_skip"] = True
            return
        app = objects.get(app_key)
        if app:
            if not app["metadata"].get("deletionTimestamp"):
                app["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
                app["metadata"]["resourceVersion"] = str(
                    int(app["metadata"]["resourceVersion"]) + 1
                )
            if skipped(app):
                current["tuppr_finalizer_stalled_on_skip"] = True
                return
        for key in [deployment_key, app_key, appset_key, root_key]:
            objects.pop(key, None)
        current["root_finalizer_completed"] = True
    elif current.get("fresh_generated_objects") and not skipped(root_app):
        journal = json.loads(
            objects["/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"][
                "data"
            ]["journal.json"]
        )
        assert journal["phase"] == "native-critical-complete"
        objects.update(current.pop("fresh_generated_objects"))
        root_app["status"] = current["fresh_root_status"]
        current["fresh_handoff_after_critical_completion"] = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, value, code=200):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/identity":
            current = state()
            current["events"].append(
                {
                    "method": "AUTH",
                    "path": path,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            save(current)
            if self.headers.get("Authorization") != current.get(
                "identity_authorization"
            ):
                return self.respond(
                    {"message": "synthetic authentication failure"}, 403
                )
            return self.respond({"login": "fixture-user"})
        if path == "/version":
            return self.respond({"major": "1", "minor": "35", "gitVersion": "v1.35.0"})
        if path == "/api":
            return self.respond(
                {"kind": "APIVersions", "apiVersion": "v1", "versions": ["v1"]}
            )
        if path == "/apis":
            if "objects" in state():
                return self.respond(
                    {
                        "kind": "APIGroupList",
                        "apiVersion": "v1",
                        "groups": [
                            {
                                "name": group,
                                "versions": [
                                    {
                                        "groupVersion": group + "/" + version,
                                        "version": version,
                                    }
                                ],
                                "preferredVersion": {
                                    "groupVersion": group + "/" + version,
                                    "version": version,
                                },
                            }
                            for group, version in [
                                ("coordination.k8s.io", "v1"),
                                ("apps", "v1"),
                                ("batch", "v1"),
                                ("argoproj.io", "v1alpha1"),
                                ("tuppr.home-operations.com", "v1alpha1"),
                                ("apiextensions.k8s.io", "v1"),
                                ("cert-manager.io", "v1"),
                                ("external-secrets.io", "v1"),
                                ("k8s.cni.cncf.io", "v1"),
                            ]
                        ],
                    }
                )
            return self.respond(
                {
                    "kind": "APIGroupList",
                    "apiVersion": "v1",
                    "groups": [
                        {
                            "name": "external-secrets.io",
                            "versions": [
                                {
                                    "groupVersion": "external-secrets.io/v1",
                                    "version": "v1",
                                }
                            ],
                            "preferredVersion": {
                                "groupVersion": "external-secrets.io/v1",
                                "version": "v1",
                            },
                        },
                        {
                            "name": "argoproj.io",
                            "versions": [
                                {
                                    "groupVersion": "argoproj.io/v1alpha1",
                                    "version": "v1alpha1",
                                }
                            ],
                            "preferredVersion": {
                                "groupVersion": "argoproj.io/v1alpha1",
                                "version": "v1alpha1",
                            },
                        },
                    ],
                }
            )
        if path in (
            "/api/v1",
            "/apis/coordination.k8s.io/v1",
            "/apis/external-secrets.io/v1",
            "/apis/argoproj.io/v1alpha1",
            "/apis/apps/v1",
            "/apis/batch/v1",
            "/apis/tuppr.home-operations.com/v1alpha1",
            "/apis/apiextensions.k8s.io/v1",
            "/apis/cert-manager.io/v1",
            "/apis/k8s.cni.cncf.io/v1",
        ):
            resources = (
                [
                    ("secrets", "Secret", True),
                    ("configmaps", "ConfigMap", True),
                    ("pods", "Pod", True),
                    ("persistentvolumeclaims", "PersistentVolumeClaim", True),
                    ("nodes", "Node", False),
                    ("namespaces", "Namespace", False),
                    ("persistentvolumes", "PersistentVolume", False),
                ]
                if path == "/api/v1"
                else [
                    ("clustersecretstores", "ClusterSecretStore", False),
                    ("externalsecrets", "ExternalSecret", True),
                ]
            )
            if path == "/apis/argoproj.io/v1alpha1":
                resources = [
                    ("applications", "Application", True),
                    ("applicationsets", "ApplicationSet", True),
                ]
            if path == "/apis/apps/v1":
                resources = [
                    ("deployments", "Deployment", True),
                    ("statefulsets", "StatefulSet", True),
                    ("deployments/scale", "Scale", True),
                    ("statefulsets/scale", "Scale", True),
                ]
            if path == "/apis/apiextensions.k8s.io/v1":
                resources = [
                    ("customresourcedefinitions", "CustomResourceDefinition", False)
                ]
            if path == "/apis/cert-manager.io/v1":
                resources = [
                    ("issuers", "Issuer", True),
                    ("certificates", "Certificate", True),
                ]
            if path == "/apis/k8s.cni.cncf.io/v1":
                resources = [
                    (
                        "network-attachment-definitions",
                        "NetworkAttachmentDefinition",
                        True,
                    )
                ]
            if path == "/apis/coordination.k8s.io/v1":
                resources = [("leases", "Lease", True)]
            if path == "/apis/tuppr.home-operations.com/v1alpha1":
                resources = [
                    ("talosupgrades", "TalosUpgrade", False),
                    ("kubernetesupgrades", "KubernetesUpgrade", False),
                ]
            if path == "/apis/batch/v1":
                resources = [("jobs", "Job", True)]
            return self.respond(
                {
                    "kind": "APIResourceList",
                    "apiVersion": "v1",
                    "groupVersion": "v1"
                    if path == "/api/v1"
                    else path.removeprefix("/apis/"),
                    "resources": [
                        {
                            "name": name,
                            "singularName": "",
                            "kind": kind,
                            "namespaced": namespaced,
                            "verbs": [
                                "get",
                                "list",
                                "patch",
                                "create",
                                "delete",
                                "update",
                            ],
                        }
                        for name, kind, namespaced in resources
                    ],
                }
            )
        if "objects" in state():
            return self.objects("GET")
        current = state()
        current["reads"].append(path)
        save(current)
        if path not in current["allowed_reads"]:
            return self.respond(
                {"kind": "Status", "message": "unexpected fixture target", "code": 422},
                422,
            )
        time.sleep(current.get("read_delays", {}).get(path, 0))
        name = path.rsplit("/", 1)[-1]
        if path.endswith("/applications/root"):
            current["root_reads"] = current.get("root_reads", 0) + 1
            save(current)
            revision = (
                "synthetic-old-head"
                if current["scenario"] == "root-advanced" and current["root_reads"] > 1
                else "synthetic-merged-head"
            )
            return self.respond(
                {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "Application",
                    "metadata": {"name": "root", "namespace": "argocd"},
                    "spec": {"sources": [{}, {}, {}]},
                    "status": {
                        "sync": {"status": "Synced", "revisions": [revision] * 3}
                    },
                }
            )
        if path.endswith("/applicationsets/apps"):
            current["appset_reads"] = current.get("appset_reads", 0) + 1
            save(current)
            uid = (
                "new-appset-owner"
                if current["scenario"] == "appset-recreated"
                and current["appset_reads"] > 1
                else "fixture-appset-owner"
            )
            return self.respond(
                {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "ApplicationSet",
                    "metadata": {"name": "apps", "namespace": "argocd", "uid": uid},
                }
            )
        if path.endswith("/applications"):
            return self.respond(
                {
                    "apiVersion": "argoproj.io/v1alpha1",
                    "kind": "ApplicationList",
                    "items": [
                        {
                            "apiVersion": "argoproj.io/v1alpha1",
                            "kind": "Application",
                            "metadata": {
                                "name": item,
                                "namespace": "argocd",
                                "ownerReferences": [{"uid": "fixture-appset-owner"}],
                            },
                        }
                        for item in current["applications"]
                    ],
                }
            )
        if path.startswith("/api/v1/namespaces/") and "/secrets/" in path:
            namespace = path.split("/")[4]
            if (
                current["scenario"] == "previous-read-failure"
                and name == "bitwarden-credentials"
            ) or (
                current["scenario"] == "target-read-failure"
                and name != "bitwarden-credentials"
            ):
                return self.respond(
                    {
                        "kind": "Status",
                        "apiVersion": "v1",
                        "message": "SYNTHETIC-PRIVATE-API-DIAGNOSTIC",
                        "reason": "Forbidden",
                        "code": 403,
                    },
                    403,
                )
            data = (
                {"token": current["token"]}
                if name == "bitwarden-credentials"
                else current["target_keys"]
            )
            if (
                current["scenario"] == "malformed-previous-token"
                and name == "bitwarden-credentials"
            ):
                data = {"token": "not-base64!"}
            if (
                current["scenario"] == "missing-previous-token"
                and name == "bitwarden-credentials"
            ):
                data = {}
            return self.respond(
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {
                        "name": name,
                        "namespace": namespace,
                        "resourceVersion": "1",
                        "uid": "fixture-secret",
                    },
                    "data": data,
                    "type": "Opaque",
                }
            )
        if "/clustersecretstores/" in path:
            if current["scenario"] == "store-read-failure":
                return self.respond(
                    {
                        "kind": "Status",
                        "apiVersion": "v1",
                        "message": "SYNTHETIC-PRIVATE-API-DIAGNOSTIC",
                        "reason": "Forbidden",
                        "code": 403,
                    },
                    403,
                )
            return self.respond(
                {
                    "apiVersion": "external-secrets.io/v1",
                    "kind": "ClusterSecretStore",
                    "metadata": {"name": name},
                    "status": {"conditions": [{"type": "Ready", "status": "True"}]},
                }
            )
        if "/externalsecrets/" in path:
            if current["scenario"] == "es-read-failure":
                return self.respond(
                    {
                        "kind": "Status",
                        "apiVersion": "v1",
                        "message": "SYNTHETIC-PRIVATE-API-DIAGNOSTIC",
                        "reason": "Forbidden",
                        "code": 403,
                    },
                    403,
                )
            ready = (
                "False"
                if current["scenario"] in ("reconciliation-failure", "restore-failure")
                else "True"
            )
            return self.respond(
                {
                    "apiVersion": "external-secrets.io/v1",
                    "kind": "ExternalSecret",
                    "metadata": {"name": name, "namespace": path.split("/")[5]},
                    "status": {
                        "refreshTime": "2100-01-01T00:00:00Z",
                        "conditions": [{"type": "Ready", "status": ready}],
                    },
                }
            )
        self.respond(
            {
                "kind": "Status",
                "apiVersion": "v1",
                "status": "Failure",
                "reason": "NotFound",
                "code": 404,
            },
            404,
        )

    def do_PATCH(self):
        if "objects" in state():
            return self.objects("PATCH")
        current = state()
        path = urlsplit(self.path).path
        if path != current["credential_path"]:
            return self.respond(
                {
                    "kind": "Status",
                    "message": "unexpected fixture patch target",
                    "code": 422,
                },
                422,
            )
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        value = payload.get("data", {}).get("token")
        if "token" in payload.get("stringData", {}):
            value = base64.b64encode(payload["stringData"]["token"].encode()).decode()
        if value is None or (
            set(payload.get("data", {})) | set(payload.get("stringData", {}))
        ) != {"token"}:
            return self.respond(
                {
                    "kind": "Status",
                    "message": "fixture rejects broad secret patch",
                    "code": 422,
                },
                422,
            )
        current["patches"].append(value)
        current["patch_paths"].append(path)
        current["token"] = value
        save(current)
        if current["scenario"] == "ambiguous-patch" and len(current["patches"]) == 1:
            return self.respond(
                {
                    "kind": "Status",
                    "apiVersion": "v1",
                    "status": "Failure",
                    "reason": "InternalError",
                    "message": "SYNTHETIC-PRIVATE-API-DIAGNOSTIC",
                    "code": 500,
                },
                500,
            )
        if current["scenario"] == "restore-failure" and len(current["patches"]) > 1:
            return self.respond(
                {
                    "kind": "Status",
                    "apiVersion": "v1",
                    "status": "Failure",
                    "message": "SYNTHETIC-PRIVATE-API-DIAGNOSTIC",
                    "code": 500,
                },
                500,
            )
        return self.respond(
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {
                    "name": "bitwarden-credentials",
                    "namespace": "platform-system",
                    "resourceVersion": "2",
                },
                "data": {"token": value},
            }
        )

    def do_POST(self):
        self.objects("POST")

    def do_PUT(self):
        self.objects("PUT")

    def do_DELETE(self):
        self.objects("DELETE")

    def objects(self, method):
        current = state()
        url = urlsplit(self.path)
        path = url.path
        body = (
            json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}"
            )
            if method != "GET"
            else None
        )
        current["events"].append(
            {"method": method, "path": path, "query": parse_qs(url.query), "body": body}
        )
        save(current)
        failure = current.get("failure")
        if (
            failure
            and failure["method"] == method
            and failure["path"] in path
            and (
                failure.get("replicas") is None
                or body.get("spec", {}).get("replicas") == failure["replicas"]
            )
            and (
                not failure.get("after")
                or any(
                    event["method"] == failure["after"] for event in current["events"]
                )
            )
        ):
            return self.respond(
                {
                    "kind": "Status",
                    "apiVersion": "v1",
                    "reason": "Forbidden",
                    "message": "synthetic boundary failure",
                    "code": 403,
                },
                403,
            )
        objects = (
            copy.deepcopy(current["objects"])
            if parse_qs(url.query).get("dryRun") == ["All"]
            else current["objects"]
        )
        scale = path.endswith("/scale")
        key = path.removesuffix("/scale")
        root_key = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        journal_key = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        root_intent = (
            json.loads(
                objects.get(journal_key, {}).get("data", {}).get("journal.json", "{}")
            )
            .get("new_root", {})
            .get("state")
            == "intent"
        )
        if (
            current.get("root_creation_race") == "get"
            and method == "GET"
            and key == root_key
            and root_intent
        ):
            objects[key] = copy.deepcopy(current["foreign_root"])
            current["root_creation_race"] = "injected"
            save(current)
        if (
            method == "PUT"
            and key == root_key
            and not body.get("metadata", {}).get("resourceVersion")
        ):
            current["root_missing_rv_put_rejected"] = True
            save(current)
            return self.respond(
                {
                    "kind": "Status",
                    "reason": "Invalid",
                    "message": "metadata.resourceVersion must be specified for an update",
                    "code": 422,
                },
                422,
            )
        if (
            method == "GET"
            and key == root_key
            and current.get("fail_native_handoff")
            and key in objects
        ):
            phase = json.loads(
                objects.get(journal_key, {}).get("data", {}).get("journal.json", "{}")
            ).get("phase")
            if phase == "native-critical-complete":
                objects[key]["status"]["sync"]["revisions"] = ["b" * 40] * 3
                save(current)
        if method == "GET":
            if key == "/api/v1/nodes" and current.get("fresh_api_pending"):
                return self.respond(
                    {"kind": "Status", "reason": "ServiceUnavailable", "code": 503}, 503
                )
            if key in objects:
                value = objects[key]
                if (
                    current.get("duplicate_appset")
                    and value["kind"] == "ApplicationSet"
                ):
                    return self.respond(
                        {
                            "apiVersion": value["apiVersion"],
                            "kind": "ApplicationSetList",
                            "items": [value, copy.deepcopy(value)],
                        }
                    )
                if scale:
                    value = {
                        "apiVersion": "autoscaling/v1",
                        "kind": "Scale",
                        "metadata": value["metadata"],
                        "spec": {"replicas": value["spec"]["replicas"]},
                        "status": {"replicas": value["spec"]["replicas"]},
                    }
                return self.respond(value)
            plural = path.rsplit("/", 1)[-1]
            candidates = [
                value
                for name, value in objects.items()
                if name.rsplit("/", 1)[0] == path
                or ("/namespaces/" not in path and name.rsplit("/", 2)[-2] == plural)
            ]
            selector = parse_qs(url.query).get("labelSelector", [""])[0]
            if selector:
                label, value = selector.split("=", 1)
                candidates = [
                    item
                    for item in candidates
                    if item["metadata"].get("labels", {}).get(label) == value
                ]
            collections = (
                "pods",
                "jobs",
                "deployments",
                "statefulsets",
                "applications",
                "applicationsets",
                "persistentvolumeclaims",
                "nodes",
                "namespaces",
                "leases",
                "configmaps",
            )
            if plural in collections:
                return self.respond(
                    {"apiVersion": "v1", "kind": "List", "items": candidates}
                )
        elif method == "DELETE" and key in objects:
            for field, expected in body.get("preconditions", {}).items():
                if objects[key]["metadata"].get(field) != expected:
                    return self.respond(
                        {"kind": "Status", "reason": "Conflict", "code": 409}, 409
                    )
            if current.get("model_root_cascade") and key.endswith("/applications/root"):
                namespace = objects["/api/v1/namespaces/selfhosted"]
                retained = "Delete=false" in namespace["metadata"].get(
                    "annotations", {}
                ).get("argocd.argoproj.io/sync-options", "").split(",")
                current["root_cascade_retained_namespace"] = retained
                if not retained:
                    namespace["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
                    for child_path, child in list(objects.items()):
                        if "/namespaces/selfhosted/" not in child_path:
                            continue
                        if child["metadata"].get("finalizers"):
                            child["metadata"]["deletionTimestamp"] = (
                                "2026-01-01T00:00:00Z"
                            )
                        else:
                            del objects[child_path]
                    objects[key]["metadata"]["deletionTimestamp"] = (
                        "2026-01-01T00:00:00Z"
                    )
                    save(current)
                    return self.respond(objects[key])
            if current.get("model_root_cascade") and key.endswith("/applications/root"):
                objects[key]["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
                objects[key]["metadata"]["resourceVersion"] = str(
                    int(objects[key]["metadata"]["resourceVersion"]) + 1
                )
                if current.get("destroy_application_race") == "destroy-foreign-root":
                    objects[key]["metadata"]["uid"] = "foreign-root"
                    current["foreign_deleting_root"] = copy.deepcopy(objects[key])
                elif (
                    current.get("destroy_application_race")
                    == "destroy-nondeleting-root"
                ):
                    objects[key]["metadata"].pop("deletionTimestamp")
                response = copy.deepcopy(objects[key])
                advance_native_lifecycle(current)
                save(current)
                return self.respond(response)
            if objects[key]["metadata"].get("finalizers") and objects[key]["kind"] in {
                "Lease",
                "ConfigMap",
            }:
                objects[key]["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
                save(current)
                return self.respond(objects[key])
            del objects[key]
            save(current)
            return self.respond(
                {"apiVersion": "v1", "kind": "Status", "status": "Success"}
            )
        elif method == "POST":
            key = path + "/" + body["metadata"]["name"]
            if key not in current["allowed_creates"]:
                return self.respond(
                    {
                        "apiVersion": "v1",
                        "kind": "Status",
                        "reason": "Forbidden",
                        "message": "unexpected fixture create target",
                        "code": 422,
                    },
                    422,
                )
            if current.get("root_creation_race") == "post" and key == root_key:
                objects[key] = copy.deepcopy(current["foreign_root"])
                current["root_creation_race"] = "injected"
                save(current)
            if key in objects:
                return self.respond(
                    {
                        "apiVersion": "v1",
                        "kind": "Status",
                        "reason": "AlreadyExists",
                        "code": 409,
                    },
                    409,
                )
            if body["kind"] in {"Lease", "ConfigMap", "Namespace", "Application"}:
                body["metadata"].update(
                    uid="created-" + body["metadata"]["name"], resourceVersion="1"
                )
            objects[key] = body
            if body["kind"] == "Job":
                pod = {
                    "apiVersion": "v1",
                    "kind": "Pod",
                    "metadata": {
                        "name": "restore-pod",
                        "namespace": body["metadata"]["namespace"],
                        "labels": {"job-name": body["metadata"]["name"]},
                    },
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [{"ready": True}],
                    },
                }
                objects[
                    "/api/v1/namespaces/"
                    + body["metadata"]["namespace"]
                    + "/pods/restore-pod"
                ] = pod
            if body["kind"] == "Pod":
                body["status"] = {"phase": "Succeeded"}
            save(current)
            return self.respond(body, 201)
        elif method in {"PATCH", "PUT"} and key in objects:
            value = objects[key]
            if isinstance(body, list):
                try:
                    value = jsonpatch.apply_patch(value, body)
                except jsonpatch.JsonPatchException, KeyError:
                    return self.respond(
                        {"kind": "Status", "reason": "Conflict", "code": 409}, 409
                    )
                if "resourceVersion" in value["metadata"]:
                    value["metadata"]["resourceVersion"] = str(
                        int(value["metadata"]["resourceVersion"]) + 1
                    )
                objects[key] = value
            else:

                def merge(target, patch):
                    for name, content in patch.items():
                        if isinstance(content, dict):
                            merge(target.setdefault(name, {}), content)
                        else:
                            target[name] = content

                merge(value, body)
            if (
                value["kind"] in ("Deployment", "StatefulSet")
                and "replicas" in value["spec"]
            ):
                replicas = value["spec"]["replicas"]
                value["metadata"]["generation"] = 1
                value["status"] = {
                    "observedGeneration": 1,
                    "replicas": replicas,
                    "availableReplicas": replicas,
                    "updatedReplicas": replicas,
                    "readyReplicas": replicas,
                }
            if (
                current.get("model_owned_fence_drift")
                and not current.get("root_owned_fence_status_refresh")
                and value["kind"] == "ApplicationSet"
                and value["spec"].get("syncPolicy", {}).get("applicationsSync")
                == "create-only"
                and root_key in objects
            ):
                root_app = objects[root_key]
                root_app["status"]["sync"]["status"] = "OutOfSync"
                root_app["status"]["resources"] = [
                    {
                        "group": "argoproj.io",
                        "kind": "ApplicationSet",
                        "namespace": "argocd",
                        "name": "apps",
                        "status": "OutOfSync",
                    }
                ]
                root_app["metadata"]["resourceVersion"] = str(
                    int(root_app["metadata"]["resourceVersion"]) + 1
                )
                current["root_owned_fence_status_refresh"] = True
                if current.get("retention_drift") == "destroy-changed-revision":
                    root_app["status"]["sync"]["revisions"] = ["b" * 40] * 3
                elif current.get("retention_drift") == "destroy-foreign-source":
                    root_app["spec"]["sources"][0]["targetRevision"] = "foreign"
                elif current.get("retention_drift") == "destroy-unrelated-drift":
                    root_app["status"]["resources"].append(
                        {
                            "group": "",
                            "kind": "Namespace",
                            "name": "foreign",
                            "status": "OutOfSync",
                        }
                    )
            advance_native_lifecycle(current)
            save(current)
            if scale:
                value = {
                    "apiVersion": "autoscaling/v1",
                    "kind": "Scale",
                    "metadata": value["metadata"],
                    "spec": {"replicas": value["spec"]["replicas"]},
                    "status": {"replicas": value["spec"]["replicas"]},
                }
            return self.respond(value)
        self.respond(
            {"apiVersion": "v1", "kind": "Status", "reason": "NotFound", "code": 404},
            404,
        )


class LoopbackHTTPServer(HTTPServer):
    def server_bind(self):
        # HTTPServer normally reverse-resolves the bind address. This local-only
        # fixture must start even when the host's DNS resolver is unavailable.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
server.timeout = 0.2
(root / "api-port").write_text(str(server.server_address[1]))
while not (root / "api-stop").exists():
    server.handle_request()
server.server_close()
