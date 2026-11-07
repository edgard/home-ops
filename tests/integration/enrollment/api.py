"""Run the actual maintenance role against a synthetic Kubernetes HTTP API.

This file-local extension covers Lease/ConfigMap discovery and CAS JSON patches,
which the older restore fixture intentionally does not implement.
"""

import base64
import hashlib
import json
import struct
import threading
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import jsonpatch
import yaml

RESOURCES = {
    "v1": {
        "ConfigMap": "configmaps",
        "Pod": "pods",
        "Node": "nodes",
        "Secret": "secrets",
        "Service": "services",
        "ServiceAccount": "serviceaccounts",
    },
    "discovery.k8s.io/v1": {"EndpointSlice": "endpointslices"},
    "apps/v1": {"Deployment": "deployments", "StatefulSet": "statefulsets"},
    "batch/v1": {"Job": "jobs", "CronJob": "cronjobs"},
    "argoproj.io/v1alpha1": {
        "Application": "applications",
        "ApplicationSet": "applicationsets",
    },
    "coordination.k8s.io/v1": {"Lease": "leases"},
    "authentication.k8s.io/v1": {"SelfSubjectReview": "selfsubjectreviews"},
    "tuppr.home-operations.com/v1alpha1": {
        "TalosUpgrade": "talosupgrades",
        "KubernetesUpgrade": "kubernetesupgrades",
    },
}


def path_for(obj):
    version = obj["apiVersion"]
    prefix = "/api/v1" if version == "v1" else "/apis/" + version
    metadata = obj["metadata"]
    return (
        prefix
        + ("/namespaces/" + metadata["namespace"] if "namespace" in metadata else "")
        + "/"
        + RESOURCES[version][obj["kind"]]
        + "/"
        + metadata["name"]
    )


@contextmanager
def maintenance_api(tmp_path, objects):
    objects = deepcopy(objects)
    if not any(row["kind"] == "Node" for row in objects):
        node = obj("Node", "node", "")
        node["metadata"].pop("namespace")
        node["status"] = {"conditions": [{"type": "Ready", "status": "True"}]}
        objects.append(node)
    if not any(
        row["kind"] == "ServiceAccount" and row["metadata"]["namespace"] == "selfhosted"
        for row in objects
    ):
        objects.append(obj("ServiceAccount", "shared-data", "selfhosted"))
    state = {
        "objects": {path_for(row): deepcopy(row) for row in objects},
        "events": [],
        "token_identities": {},
    }
    for pod in objects:
        if pod["kind"] != "Pod":
            continue
        meta = pod["metadata"]
        sa = next(
            (
                row
                for row in objects
                if row["kind"] == "ServiceAccount"
                and row["metadata"]["name"] == pod["spec"].get("serviceAccountName")
                and row["metadata"].get("namespace") == meta["namespace"]
            ),
            {},
        )
        node = next(
            (
                row
                for row in objects
                if row["kind"] == "Node"
                and row["metadata"]["name"] == pod["spec"].get("nodeName")
            ),
            {},
        )
        state["token_identities"]["Bearer fixture-" + meta["name"]] = {
            "uid": sa.get("metadata", {}).get("uid", ""),
            "username": "system:serviceaccount:"
            + meta["namespace"]
            + ":"
            + pod["spec"].get("serviceAccountName", ""),
            "extra": {
                "authentication.kubernetes.io/" + key: [value]
                for key, value in {
                    "pod-name": meta["name"],
                    "pod-uid": meta["uid"],
                    "node-name": pod["spec"].get("nodeName", ""),
                    "node-uid": node.get("metadata", {}).get("uid", ""),
                }.items()
            },
        }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, obj, code=200):
            value = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(value)))
            self.end_headers()
            self.wfile.write(value)

        def do_GET(self):
            path = urlsplit(self.path).path
            if (
                path.endswith("/exec")
                and self.headers.get("Upgrade", "").lower() == "websocket"
            ):
                command = parse_qs(urlsplit(self.path).query).get("command", [])
                state["events"].append(
                    {"method": "EXEC", "path": path, "command": command}
                )
                rc, stdout = state.get("exec_reply", lambda *_: (1, ""))(command, state)
                accept = base64.b64encode(
                    hashlib.sha1(
                        (
                            self.headers["Sec-WebSocket-Key"]
                            + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                        ).encode()
                    ).digest()
                ).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.send_header("Sec-WebSocket-Protocol", "v4.channel.k8s.io")
                self.end_headers()
                status = (
                    {"status": "Success"}
                    if rc == 0
                    else {
                        "status": "Failure",
                        "details": {
                            "causes": [{"reason": "ExitCode", "message": str(rc)}]
                        },
                    }
                )
                for payload in [
                    b"\x01" + stdout.encode(),
                    b"\x03" + json.dumps(status).encode(),
                ]:
                    self.wfile.write(
                        bytes([0x82, len(payload)]) + payload
                        if len(payload) < 126
                        else bytes([0x82, 126])
                        + struct.pack("!H", len(payload))
                        + payload
                    )
                    self.wfile.flush()
                self.wfile.write(b"\x88\x00")
                self.wfile.flush()
                self.close_connection = True
                return
            if path == "/version":
                return self.respond(
                    {"major": "1", "minor": "35", "gitVersion": "v1.35.0"}
                )
            if path == "/api":
                return self.respond({"kind": "APIVersions", "versions": ["v1"]})
            if path == "/apis":
                return self.respond(
                    {
                        "kind": "APIGroupList",
                        "groups": [
                            {
                                "name": version.split("/")[0],
                                "versions": [
                                    {
                                        "groupVersion": version,
                                        "version": version.split("/")[1],
                                    }
                                ],
                                "preferredVersion": {
                                    "groupVersion": version,
                                    "version": version.split("/")[1],
                                },
                            }
                            for version in RESOURCES
                            if version != "v1"
                            and not (
                                state.get("missing_upgrade_api")
                                and version.startswith("tuppr.")
                            )
                        ],
                    }
                )
            version = "v1" if path == "/api/v1" else path.removeprefix("/apis/")
            if version in RESOURCES:
                return self.respond(
                    {
                        "kind": "APIResourceList",
                        "groupVersion": version,
                        "resources": [
                            {
                                "name": plural,
                                "kind": kind,
                                "namespaced": kind
                                not in {
                                    "Node",
                                    "TalosUpgrade",
                                    "KubernetesUpgrade",
                                    "SelfSubjectReview",
                                },
                                "singularName": "",
                                "verbs": [
                                    "get",
                                    "list",
                                    "create",
                                    "patch",
                                    "update",
                                    "delete",
                                ],
                            }
                            for kind, plural in RESOURCES[version].items()
                        ],
                    }
                )
            if path == "/apis/batch/v1/jobs":
                state["jobs_read_seen"] = True
            if (
                path == "/api/v1/pods"
                and state.get("jobs_read_seen")
                and state.get("late_cron")
                and not state.get("late_cron_injected")
            ):
                for late in state["late_cron"]:
                    state["objects"][path_for(late)] = deepcopy(late)
                state["late_cron_injected"] = True
            state["events"].append({"method": "GET", "path": path})
            if state.get("on_get"):
                state["on_get"](path, state)
            if path in state["objects"]:
                return self.respond(state["objects"][path])
            if path.rsplit("/", 1)[-1] in {
                plural for rows in RESOURCES.values() for plural in rows.values()
            }:
                selector = parse_qs(urlsplit(self.path).query).get(
                    "labelSelector", [""]
                )[0]
                values = [
                    obj
                    for key, obj in state["objects"].items()
                    if key.rsplit("/", 1)[0] == path
                    or (
                        "/namespaces/" not in path
                        and key.rsplit("/", 2)[-2] == path.rsplit("/", 1)[-1]
                    )
                ]
                values = [
                    obj
                    for obj in values
                    if all(
                        obj["metadata"].get("labels", {}).get(k) == v
                        for k, v in (
                            part.split("=", 1) for part in selector.split(",") if part
                        )
                    )
                ]
                return self.respond(
                    {"apiVersion": "v1", "kind": "List", "items": values}
                )
            return self.respond(
                {"kind": "Status", "reason": "NotFound", "code": 404}, 404
            )

        def mutate(self, method):
            path = urlsplit(self.path).path
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["events"].append(
                {"method": method, "path": path, "body": deepcopy(body)}
            )
            if (
                state.get("fail_scale_path") == path
                and isinstance(body, list)
                and any(
                    row.get("path") == "/spec/replicas" and row.get("value") == 0
                    for row in body
                )
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            if (
                state.get("fail_template")
                and isinstance(body, list)
                and any(
                    row.get("path") == "/spec/template" and row.get("op") == "add"
                    for row in body
                )
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            journal_payload = (
                body.get("data", {}).get("journal.json")
                if isinstance(body, dict)
                else next(
                    (
                        row.get("value")
                        for row in body
                        if row.get("path") == "/data/journal.json"
                    ),
                    None,
                )
            )
            if (
                state.get("fail_completion")
                and journal_payload
                and json.loads(journal_payload)["phase"] == "complete"
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            if method == "POST":
                if (
                    "name" not in body["metadata"]
                    and "generateName" in body["metadata"]
                ):
                    body["metadata"]["name"] = (
                        body["metadata"]["generateName"] + "unique"
                    )
                path += "/" + body["metadata"]["name"]
                if path in state["objects"]:
                    return self.respond(
                        {"kind": "Status", "reason": "AlreadyExists", "code": 409}, 409
                    )
                body["metadata"].update(
                    uid="created-" + body["metadata"]["name"], resourceVersion="1"
                )
                state["objects"][path] = body
                if state.get("created"):
                    state["created"](body, state)
                if body["kind"] == "Job" and state.get("job_created"):
                    state["job_created"](body, state)
                return self.respond(body, 201)
            if (
                method == "PATCH"
                and path not in state["objects"]
                and self.headers.get("Content-Type", "").startswith(
                    "application/apply-patch"
                )
            ):
                body["metadata"].update(
                    uid="created-" + body["metadata"]["name"], resourceVersion="1"
                )
                state["objects"][path] = body
                return self.respond(body, 201)
            try:
                value = state["objects"][path]
                if isinstance(body, list):
                    value = jsonpatch.apply_patch(value, body)
                else:

                    def merge(target, patch):
                        for key, content in patch.items():
                            if isinstance(content, dict):
                                merge(target.setdefault(key, {}), content)
                            elif content is None:
                                target.pop(key, None)
                            else:
                                target[key] = content

                    merge(value, body)
                value["metadata"]["resourceVersion"] = str(
                    int(value["metadata"]["resourceVersion"]) + 1
                )
                if value["kind"] in {"Deployment", "StatefulSet"}:
                    replicas = value["spec"].get("replicas", 1)
                    value["status"] = {"replicas": replicas, "readyReplicas": replicas}
                state["objects"][path] = value
                if state.get("patched"):
                    state["patched"](path, value, state)
                if (
                    state.get("ambiguous_completion")
                    and journal_payload
                    and json.loads(journal_payload)["phase"] == "complete"
                ):
                    state["ambiguous_completion"] = False
                    return self.respond(
                        {"kind": "Status", "reason": "InternalError", "code": 500}, 500
                    )
                return self.respond(value)
            except jsonpatch.JsonPatchException, KeyError:
                return self.respond(
                    {"kind": "Status", "reason": "Conflict", "code": 409}, 409
                )

        def do_DELETE(self):
            path = urlsplit(self.path).path
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size)) if size else {}
            state["events"].append({"method": "DELETE", "path": path, "body": body})
            current = state["objects"].get(path)
            if not current:
                return self.respond(
                    {"kind": "Status", "reason": "NotFound", "code": 404}, 404
                )
            expected = body.get("preconditions", {}).get("uid")
            if not expected or current["metadata"]["uid"] != expected:
                return self.respond(
                    {"kind": "Status", "reason": "Conflict", "code": 409}, 409
                )
            if state.get("hang_pods") and current["kind"] == "Pod":
                current["metadata"]["deletionTimestamp"] = "2026-01-01T00:00:00Z"
                return self.respond(current)
            del state["objects"][path]
            return self.respond(
                {"apiVersion": "v1", "kind": "Status", "status": "Success", "code": 200}
            )

        def do_POST(self):
            if (
                urlsplit(self.path).path
                == "/apis/authentication.k8s.io/v1/selfsubjectreviews"
            ):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                state["events"].append(
                    {"method": "IDENTITY", "path": self.path, "body": body}
                )
                return self.respond(
                    {
                        "apiVersion": "authentication.k8s.io/v1",
                        "kind": "SelfSubjectReview",
                        "metadata": {},
                        "status": {
                            "userInfo": state["token_identities"].get(
                                self.headers.get("Authorization"), {}
                            )
                        },
                    },
                    201,
                )
            self.mutate("POST")

        def do_PATCH(self):
            self.mutate("PATCH")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    kubeconfig = tmp_path / "kubeconfig"
    kubeconfig.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "clusters": [
                    {
                        "name": "fixture",
                        "cluster": {"server": f"http://127.0.0.1:{server.server_port}"},
                    }
                ],
                "contexts": [
                    {
                        "name": "fixture-" + pod["metadata"]["name"],
                        "context": {
                            "cluster": "fixture",
                            "user": pod["metadata"]["name"],
                        },
                    }
                    for pod in objects
                    if pod["kind"] == "Pod"
                ]
                + [
                    {
                        "name": "fixture",
                        "context": {"cluster": "fixture", "user": "fixture"},
                    }
                ],
                "users": [{"name": "fixture", "user": {"token": "fixture-coordinator"}}]
                + [
                    {
                        "name": pod["metadata"]["name"],
                        "user": {"token": "fixture-" + pod["metadata"]["name"]},
                    }
                    for pod in objects
                    if pod["kind"] == "Pod"
                ],
                "current-context": "fixture",
            }
        )
    )
    try:
        yield {"kubeconfig_path": str(kubeconfig), "kube_context": "fixture"}, state
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def obj(kind, name, namespace, spec=None, version=None):
    return {
        "apiVersion": version
        or next(version for version, rows in RESOURCES.items() if kind in rows),
        "kind": kind,
        "metadata": {
            "name": name,
            "namespace": namespace,
            "uid": name + "-uid",
            "resourceVersion": "1",
        },
        "spec": {
            "nodeName": "node",
            "serviceAccountName": "shared-data",
            **(spec or {}),
        }
        if kind == "Pod"
        else spec or {},
    }


def scenario_objects():
    policy = {"automated": {"selfHeal": True, "prune": True}, "retry": {"limit": 2}}
    objects = [
        obj("Application", name, "argocd", {"syncPolicy": deepcopy(policy)})
        for name in ["root", "paperless", "tuppr"]
    ]
    objects += [
        obj("ApplicationSet", "apps", "argocd", {}),
        obj(
            "Deployment",
            "tuppr",
            "platform-system",
            {"replicas": 1, "selector": {"matchLabels": {"app": "tuppr"}}},
        ),
        obj(
            "Deployment",
            "paperless",
            "selfhosted",
            {"replicas": 2, "selector": {"matchLabels": {"app": "paperless"}}},
        ),
        obj("CronJob", "export", "selfhosted", {}),
        obj("Pod", "coordinator", "selfhosted"),
    ]
    objects[-1]["status"] = {"phase": "Running"}
    variables = {
        "shared_data_confirm": True,
        "shared_data_drain_enabled": False,
        "shared_data_apps": ["paperless"],
        "shared_data_operation_id": "test-backup",
        "shared_data_operation_kind": "backup",
        "shared_data_holder_pod_name": "coordinator",
        "shared_data_holder_pod_namespace": "selfhosted",
        "shared_data_holder_pod_uid": "coordinator-uid",
        "shared_data_wait_retries": 1,
        "shared_data_wait_delay": 0,
        "shared_data_registry": {
            "version": 1,
            "consumers": {
                "paperless": {
                    "namespace": "selfhosted",
                    "enabled": True,
                    "workloads": [{"kind": "Deployment", "name": "paperless"}],
                    "cronjobs": [{"name": "export"}],
                }
            },
        },
    }
    return objects, variables
