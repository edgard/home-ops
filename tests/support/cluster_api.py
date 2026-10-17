"""Local Kubernetes HTTP fixture; synthetic values only, never a cluster client."""

import base64
import copy
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

root = Path(sys.argv[1])


def state():
    return json.loads((root / "api-state.json").read_text())


def save(value):
    (root / "api-state.json").write_text(json.dumps(value))


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
                                ("apps", "v1"),
                                ("batch", "v1"),
                                ("argoproj.io", "v1alpha1"),
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
            "/apis/external-secrets.io/v1",
            "/apis/argoproj.io/v1alpha1",
            "/apis/apps/v1",
            "/apis/batch/v1",
            "/apis/apiextensions.k8s.io/v1",
            "/apis/cert-manager.io/v1",
            "/apis/k8s.cni.cncf.io/v1",
        ):
            resources = (
                [
                    ("secrets", "Secret", True),
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
        self.objects("PATCH")

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
        if method == "GET":
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
            )
            if plural in collections:
                return self.respond(
                    {"apiVersion": "v1", "kind": "List", "items": candidates}
                )
        elif method == "DELETE" and key in objects:
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
        elif method == "PATCH" and key in objects:
            value = objects[key]
            if isinstance(body, list):
                for operation in body:
                    assert operation["op"] == "remove", "unsupported JSON patch"
                    parent = value
                    parts = operation["path"].strip("/").split("/")
                    for part in parts[:-1]:
                        parent = parent[part]
                    parent.pop(parts[-1])
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


server = HTTPServer(("127.0.0.1", 0), Handler)
server.timeout = 0.2
(root / "api-port").write_text(str(server.server_address[1]))
while not (root / "api-stop").exists():
    server.handle_request()
server.server_close()
