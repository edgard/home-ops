"""Run the actual maintenance role against a synthetic Kubernetes HTTP API.

This file-local extension covers Lease/ConfigMap discovery and CAS JSON patches,
which the older restore fixture intentionally does not implement.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import jsonpatch
import pytest
import yaml

from tests.support.runtime import load_module, run_role

RESOURCES = {
    "v1": {
        "ConfigMap": "configmaps",
        "Pod": "pods",
        "Node": "nodes",
        "Namespace": "namespaces",
        "Secret": "secrets",
        "Service": "services",
        "ServiceAccount": "serviceaccounts",
    },
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
def maintenance_api(tmp_path, objects, *, include_default_service_account=True):
    objects = deepcopy(objects)
    if not any(row["kind"] == "Node" for row in objects):
        node = obj("Node", "node", "")
        node["metadata"].pop("namespace")
        node["status"] = {"conditions": [{"type": "Ready", "status": "True"}]}
        objects.append(node)
    if include_default_service_account and not any(
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
            if path == "/version":
                return self.respond(
                    {
                        "major": "1",
                        "minor": "35",
                        "gitVersion": state.get("server_version", "v1.35.0"),
                    }
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
                                    "Namespace",
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
            if path == "/api/v1/nodes/node" and state.get("native_outage_reads", 0) > 0:
                state["native_outage_reads"] -= 1
                return self.respond(
                    {"kind": "Status", "reason": "ServiceUnavailable", "code": 503}, 503
                )
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
                state.get("fail_upload_binding")
                and journal_payload
                and json.loads(journal_payload).get("upload_job")
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            if (
                state.get("fail_completion")
                and journal_payload
                and json.loads(journal_payload)["phase"] == "complete"
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            if (
                method == "POST"
                and state.get("fail_native_journal_create")
                and journal_payload
                and json.loads(journal_payload).get("operation_kind")
                == "node-operation"
            ):
                return self.respond(
                    {"kind": "Status", "reason": "Forbidden", "code": 403}, 403
                )
            if method == "POST":
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
                if (
                    body["kind"] == "Job"
                    and not body.get("spec", {}).get("suspend")
                    and state.get("job_created")
                ):
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
                if state.get("before_patch"):
                    state["before_patch"](path, body, state)
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
                if (
                    value["kind"] == "Job"
                    and not value.get("spec", {}).get("suspend")
                    and state.get("job_created")
                    and value["metadata"]["uid"]
                    not in state.setdefault("started_jobs", set())
                ):
                    state["started_jobs"].add(value["metadata"]["uid"])
                    state["job_created"](value, state)
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


@pytest.fixture
def scenario():
    return scenario_objects()


@pytest.mark.parametrize("check,confirm", [(True, True), (False, False)])
def test_preview_and_checkmode_never_mutate(tmp_path, scenario, check, confirm):
    objects, variables = scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **variables, "shared_data_confirm": confirm},
            check=check,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_hold_resume_is_durable_and_restores_root_last(tmp_path, scenario):
    objects, variables = scenario
    originals = {
        path_for(row): deepcopy(row["spec"]) for row in objects if row["kind"] != "Pod"
    }
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold",
            {**connection, **variables},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal_path = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        journal = json.loads(state["objects"][journal_path]["data"]["journal.json"])
        assert journal["phase"] == "held"
        assert journal["holder"]["uid"] == "coordinator-uid"
        root_path = path_for(objects[0])
        mutations = [
            row
            for row in state["events"]
            if row["method"] == "PATCH" and row["path"] in originals
        ]
        assert mutations[0]["path"] == root_path
        first_root_index = state["events"].index(mutations[0])
        recorded = [
            row
            for row in state["events"][:first_root_index]
            if isinstance(row.get("body"), dict)
            and "journal.json" in row["body"].get("data", {})
        ]
        assert recorded
        assert (
            json.loads(recorded[0]["body"]["data"]["journal.json"])["phase"]
            == "recorded"
        )
        assert state["objects"][path_for(objects[5])]["spec"]["replicas"] == 0
        assert state["objects"][path_for(objects[6])]["spec"]["suspend"] is True
        assert "automated" not in state["objects"][root_path]["spec"]["syncPolicy"]
        boundary = len(state["events"])
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_resume",
            {**connection, **variables},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        for path, spec in originals.items():
            assert state["objects"][path]["spec"] == spec
        patches = [
            row
            for row in state["events"][boundary:]
            if row["method"] == "PATCH" and row["path"] in originals
        ]
        assert patches[-1]["path"] == root_path
        assert (
            json.loads(state["objects"][journal_path]["data"]["journal.json"])["phase"]
            == "complete"
        )


def test_conflicting_lease_fails_without_application_mutations(tmp_path, scenario):
    objects, variables = scenario
    objects.append(
        obj(
            "Lease",
            "shared-data-operation",
            "selfhosted",
            {"holderIdentity": "another:other"},
        )
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path, "shared_data", "maintenance_hold", {**connection, **variables}
        )
        assert result.returncode != 0
        assert not any(row["method"] in {"POST", "PATCH"} for row in state["events"])


def test_watchdog_without_journal_is_readonly_and_needs_no_scope(tmp_path, scenario):
    objects, _ = scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_watchdog",
            {**connection, "shared_data_confirm": True},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


@pytest.fixture
def held_scenario(scenario):
    objects, variables = scenario
    maintenance = load_module("shared_data/filter_plugins/maintenance.py")
    by_path = {path_for(row): row for row in objects}
    targets = maintenance.shared_data_targets(
        variables["shared_data_registry"], ["paperless"], "test-backup", "backup"
    )
    snapshots = []
    for target in targets:
        candidate = next(
            row
            for row in objects
            if row["kind"] == target["kind"]
            and row["metadata"]["name"] == target["name"]
            and row["metadata"]["namespace"] == target["namespace"]
        )
        snapshot = maintenance.shared_data_snapshot(target, candidate)
        snapshots.append(snapshot)
        by_path[path_for(candidate)] = jsonpatch.apply_patch(
            candidate, maintenance.shared_data_patch(snapshot, candidate)
        )
    journal = {
        "version": 1,
        "operation_id": "test-backup",
        "operation_kind": "backup",
        "apps": ["paperless"],
        "phase": "held",
        "recovery_result": "none",
        "holder": {
            "uid": "coordinator-uid",
            "name": "coordinator",
            "namespace": "selfhosted",
            "owners": [],
            "kind": "Pod",
            "fence_nodes": [{"name": "node", "uid": "node-uid"}],
        },
        "snapshots": snapshots,
    }
    configmap = obj("ConfigMap", "shared-data-operation", "selfhosted")
    configmap["data"] = {"journal.json": json.dumps(journal)}
    lease = obj(
        "Lease",
        "shared-data-operation",
        "selfhosted",
        {
            "holderIdentity": "test-backup:coordinator-uid",
            "renewTime": "2000-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    )
    lease["metadata"]["annotations"] = {
        "home-ops/data-coordinator": json.dumps(
            {
                "operation_id": "test-backup",
                "operation_kind": "backup",
                "actor": journal["holder"],
                "stage": "journaled",
            }
        )
    }
    return [*by_path.values(), configmap, lease], variables


@pytest.mark.parametrize(
    "kind,live,expired,success",
    [
        ("backup", False, True, True),
        ("restore", False, True, False),
        ("backup", True, True, False),
        ("backup", False, False, False),
    ],
)
def test_recovery_only_restores_expired_fenced_backup(
    tmp_path, held_scenario, kind, live, expired, success
):
    objects, variables = held_scenario
    journal_obj = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(journal_obj["data"]["journal.json"])
    journal["operation_kind"] = kind
    lease = next(row for row in objects if row["kind"] == "Lease")
    record = json.loads(lease["metadata"]["annotations"]["home-ops/data-coordinator"])
    record["operation_kind"] = kind
    lease["metadata"]["annotations"]["home-ops/data-coordinator"] = json.dumps(record)
    journal_obj["data"]["journal.json"] = json.dumps(journal)
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = (
        "Running" if live else "Failed"
    )
    if not expired:
        next(row for row in objects if row["kind"] == "Lease")["spec"]["renewTime"] = (
            "2100-01-01T00:00:00Z"
        )
    executor = recovery_executor(objects)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_watchdog",
            {
                **connection,
                "shared_data_confirm": True,
                **executor,
                "shared_data_wait_retries": 1,
                "shared_data_wait_delay": 0,
            },
            timeout=480,
        )
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        app = state["objects"][
            "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
        ]
        assert app["spec"]["replicas"] == (2 if success else 0)
        current = json.loads(
            state["objects"][path_for(journal_obj)]["data"]["journal.json"]
        )
        if success:
            assert current["phase"] == "complete"
            assert "fenced" in current["recovery_result"]
            assert current["holder"]["uid"] == "coordinator-uid"
            assert (
                current["coordinator"]["uid"] == executor["shared_data_holder_pod_uid"]
            )
            assert (
                state["objects"][
                    "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
                ]["spec"]["holderIdentity"]
                == ""
            )
        elif kind == "restore":
            assert current["recovery_result"] == "operator inspection required"
        else:
            assert not any(
                row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
            )


def test_failed_completion_refences_root_and_holds_writers(tmp_path, held_scenario):
    objects, variables = held_scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["fail_completion"] = True
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_resume",
            {**connection, **variables},
            timeout=480,
        )
        assert result.returncode != 0
        root = state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        ]
        assert "automated" not in root["spec"]["syncPolicy"]
        assert (
            state["objects"][
                "/apis/apps/v1/namespaces/selfhosted/deployments/paperless"
            ]["spec"]["replicas"]
            == 0
        )


def test_direct_hold_executor_cannot_bypass_confirmation(tmp_path, scenario):
    objects, variables = scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_hold_execute",
            {**connection, **variables, "shared_data_confirm": False},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_admin_can_finish_completed_journal_with_unreleased_lease(
    tmp_path, held_scenario
):
    objects, variables = held_scenario
    journal_obj = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(journal_obj["data"]["journal.json"])
    restore_completed_targets(objects, journal)
    journal["phase"] = "complete"
    journal_obj["data"]["journal.json"] = json.dumps(journal)
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = "Failed"
    executor = recovery_executor(objects)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_resume",
            {**connection, **variables, "shared_data_admin_resume": True, **executor},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        lease = state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]
        assert lease["spec"]["holderIdentity"] == ""


def test_missing_upgrade_api_cannot_be_mistaken_for_idle(tmp_path, scenario):
    objects, variables = scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["missing_upgrade_api"] = True
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_upgrades",
            {**connection, **variables},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


@pytest.mark.parametrize(
    "phase,mode",
    [
        ("Pending", "backoff-job"),
        ("Completed", "active-job"),
        (None, "orphan-job"),
        ("Completed", "live-pod"),
    ],
)
def test_idle_upgrade_phase_does_not_hide_independent_workers(
    tmp_path, scenario, phase, mode
):
    objects, variables = scenario
    if phase is not None:
        plan = obj("KubernetesUpgrade", "kubernetes", "platform-system")
        plan["metadata"].pop("namespace")
        plan["metadata"]["uid"] = "new-plan-uid"
        plan["status"] = {"phase": phase}
        objects.append(plan)
    job = obj(
        "Job", "upgrade-node", "platform-system", {"backoffLimit": 3, "parallelism": 1}
    )
    job["metadata"]["uid"] = "old-job-uid"
    job["metadata"]["ownerReferences"] = [
        {
            "apiVersion": "tuppr.home-operations.com/v1alpha1",
            "kind": "KubernetesUpgrade",
            "name": "kubernetes",
            "uid": "old-plan-uid",
            "controller": True,
        }
    ]
    job["metadata"]["labels"] = {
        "app.kubernetes.io/name": "kubernetes-upgrade",
        "app.kubernetes.io/part-of": "tuppr",
        "app.kubernetes.io/instance": "kubernetes",
        "tuppr.home-operations.com/target-node": "node",
    }
    job["status"] = {"active": 1 if mode == "active-job" else 0}
    if mode == "live-pod":
        job["spec"]["suspend"] = True
        job["status"]["conditions"] = [{"type": "Complete", "status": "True"}]
        pod = obj("Pod", "upgrade-worker", "platform-system")
        pod["metadata"]["ownerReferences"] = [
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "uid": "old-job-uid",
                "name": "upgrade-node",
                "controller": True,
            }
        ]
        pod["status"] = {"phase": "Running"}
        objects.append(pod)
    objects.append(job)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_upgrades",
            {**connection, **variables},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def test_cronjob_created_between_job_and_pod_reads_cannot_pass_barrier(
    tmp_path, scenario
):
    objects, variables = scenario
    job = obj("Job", "late-export", "selfhosted", {"backoffLimit": 2})
    job["metadata"]["ownerReferences"] = [
        {
            "apiVersion": "batch/v1",
            "kind": "CronJob",
            "name": "export",
            "uid": "export-uid",
            "controller": True,
        }
    ]
    job["status"] = {"active": 0}
    pod = obj("Pod", "late-export-pod", "selfhosted")
    pod["metadata"]["ownerReferences"] = [
        {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "name": "late-export",
            "uid": job["metadata"]["uid"],
            "controller": True,
        }
    ]
    pod["status"] = {"phase": "Running"}
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["late_cron"] = [job, pod]
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_wait_pods",
            {
                **connection,
                **variables,
                "shared_data_wait_targets": [
                    {"role": "cronjob", "namespace": "selfhosted", "uid": "export-uid"}
                ],
            },
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert state.get("late_cron_injected")
        assert result.returncode != 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def recovery_executor(objects, uid="watchdog-uid"):
    pod = obj("Pod", uid, "selfhosted")
    pod["metadata"]["uid"] = uid
    pod["status"] = {"phase": "Running"}
    objects.append(pod)
    return {
        "shared_data_holder_pod_name": uid,
        "shared_data_holder_pod_namespace": "selfhosted",
        "shared_data_holder_pod_uid": uid,
        "kube_context": "fixture-" + uid,
    }


def test_stale_guard_cannot_reclaim_an_emptied_lease(tmp_path, scenario):
    objects, variables = scenario
    objects.append(
        obj("Lease", "shared-data-operation", "selfhosted", {"holderIdentity": ""})
    )
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_guard",
            {**connection, **variables},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


@pytest.mark.parametrize(
    "live,expired,stage,release",
    [
        (False, True, "claimed", True),
        (True, True, "claimed", False),
        (False, False, "claimed", False),
        (False, True, "journaled", False),
    ],
)
def test_expired_fenced_orphan_claim_releases_without_journal_or_target_replay(
    tmp_path, scenario, live, expired, stage, release
):
    objects, variables = scenario
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = (
        "Running" if live else "Failed"
    )
    executor = recovery_executor(objects)
    lease = obj(
        "Lease",
        "shared-data-operation",
        "selfhosted",
        {
            "holderIdentity": "test-backup:coordinator-uid",
            "renewTime": "2000-01-01T00:00:00Z" if expired else "2100-01-01T00:00:00Z",
            "leaseDurationSeconds": 1,
        },
    )
    lease["metadata"]["annotations"] = {
        "home-ops/data-coordinator": json.dumps(
            {
                "operation_id": "test-backup",
                "operation_kind": "backup",
                "actor": {
                    "uid": "coordinator-uid",
                    "name": "coordinator",
                    "namespace": "selfhosted",
                    "owners": [],
                    "kind": "Pod",
                    "fence_nodes": [{"name": "node", "uid": "node-uid"}],
                },
                "stage": stage,
            }
        )
    }
    objects.append(lease)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_watchdog",
            {**connection, **variables, **executor},
            timeout=480,
        )
        assert (result.returncode == 0) == release, result.stdout + result.stderr
        assert state["objects"][path_for(lease)]["spec"]["holderIdentity"] == (
            "" if release else "test-backup:coordinator-uid"
        )
        writes = [
            row for row in state["events"] if row["method"] not in {"GET", "IDENTITY"}
        ]
        assert bool(writes) == release
        assert all(row["path"] == path_for(lease) for row in writes)


def test_completed_journal_cleanup_releases_lease_without_target_replay(
    tmp_path, held_scenario
):
    objects, variables = held_scenario
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = "Failed"
    executor = recovery_executor(objects)
    journal_obj = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(journal_obj["data"]["journal.json"])
    restore_completed_targets(objects, journal)
    journal["phase"] = "complete"
    journal_obj["data"]["journal.json"] = json.dumps(journal)
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_watchdog",
            {**connection, **variables, **executor},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        lease_path = "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        assert state["objects"][lease_path]["spec"]["holderIdentity"] == ""
        writes = [
            row for row in state["events"] if row["method"] not in {"GET", "IDENTITY"}
        ]
        assert writes and all(row["path"] == lease_path for row in writes)


def test_concurrent_watchdog_and_admin_have_distinct_exclusive_lease_owner(
    tmp_path, held_scenario
):
    objects, variables = held_scenario
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = "Failed"
    watchdog = recovery_executor(objects, "watchdog-live")
    admin = recovery_executor(objects, "admin-live")
    with maintenance_api(tmp_path, objects) as (connection, state):

        def invoke(name, executor, entry, extra):
            directory = tmp_path / name
            directory.mkdir()
            return run_role(
                directory,
                "shared_data",
                entry,
                {**connection, **variables, **executor, **extra},
                timeout=600,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(invoke, "watchdog", watchdog, "maintenance_recover", {})
            two = pool.submit(
                invoke,
                "admin",
                admin,
                "maintenance_resume",
                {"shared_data_admin_resume": True},
            )
            results = [one.result(), two.result()]
        assert sum(result.returncode == 0 for result in results) == 1, "\n".join(
            result.stdout + result.stderr for result in results
        )
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["holder"]["uid"] == "coordinator-uid"
        assert journal["coordinator"]["uid"] in {"watchdog-live", "admin-live"}
        assert journal["phase"] == "complete"
        winning = journal["coordinator"]["uid"]
        losing = admin if winning == "watchdog-live" else watchdog
        before = deepcopy(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]
        )
        directory = tmp_path / "stale-loser"
        directory.mkdir()
        result = run_role(
            directory,
            "shared_data",
            "maintenance_save",
            {
                **connection,
                **variables,
                **losing,
                "shared_data_journal": {**journal, "phase": "resuming"},
            },
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0
        assert (
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]
            == before
        )


@pytest.mark.parametrize(
    "entry", ["maintenance_resume_execute", "maintenance_recover_execute"]
)
def test_direct_recovery_executors_cannot_bypass_confirmation(
    tmp_path, scenario, entry
):
    objects, variables = scenario
    with maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            entry,
            {**connection, **variables, "shared_data_confirm": False},
            env={
                "K8S_AUTH_KUBECONFIG": connection["kubeconfig_path"],
                "K8S_AUTH_CONTEXT": "fixture",
            },
        )
        assert result.returncode != 0
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )


def restore_completed_targets(objects, journal):
    maintenance = load_module("shared_data/filter_plugins/maintenance.py")
    for snapshot in journal["snapshots"]:
        index = next(
            index
            for index, row in enumerate(objects)
            if row["kind"] == snapshot["kind"]
            and row["metadata"]["uid"] == snapshot["uid"]
        )
        objects[index] = jsonpatch.apply_patch(
            objects[index],
            maintenance.shared_data_patch(snapshot, objects[index], True),
        )


def test_new_orphan_claim_can_coexist_with_previous_completed_journal(
    tmp_path, held_scenario
):
    objects, variables = held_scenario
    journal_obj = next(row for row in objects if row["kind"] == "ConfigMap")
    journal = json.loads(journal_obj["data"]["journal.json"])
    restore_completed_targets(objects, journal)
    journal["phase"] = "complete"
    journal_obj["data"]["journal.json"] = json.dumps(journal)
    next(row for row in objects if row["kind"] == "Pod")["status"]["phase"] = "Failed"
    lease = next(row for row in objects if row["kind"] == "Lease")
    lease["spec"]["holderIdentity"] = "next-backup:next-coordinator"
    lease["metadata"]["annotations"] = {
        "home-ops/data-coordinator": json.dumps(
            {
                "operation_id": "next-backup",
                "operation_kind": "backup",
                "actor": {
                    "uid": "next-coordinator",
                    "name": "next-coordinator",
                    "namespace": "selfhosted",
                    "owners": [],
                    "kind": "Pod",
                    "fence_nodes": [{"name": "node", "uid": "node-uid"}],
                },
                "stage": "claimed",
            }
        )
    }
    executor = recovery_executor(objects)
    with maintenance_api(tmp_path, objects) as (connection, state):
        original_journal = deepcopy(state["objects"][path_for(journal_obj)])
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_watchdog",
            {**connection, **variables, **executor},
            timeout=480,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert state["objects"][path_for(lease)]["spec"]["holderIdentity"] == ""
        assert state["objects"][path_for(journal_obj)] == original_journal
        assert all(
            row["path"] == path_for(lease)
            for row in state["events"]
            if row["method"] not in {"GET", "IDENTITY"}
        )


def test_ambiguous_completion_cannot_release_refenced_targets_as_complete(
    tmp_path, held_scenario
):
    objects, variables = held_scenario
    executor = recovery_executor(objects)
    with maintenance_api(tmp_path, objects) as (connection, state):
        state["ambiguous_completion"] = True
        result = run_role(
            tmp_path,
            "shared_data",
            "maintenance_resume",
            {**connection, **variables},
            timeout=600,
        )
        assert result.returncode != 0
        journal_path = "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
        current = json.loads(state["objects"][journal_path]["data"]["journal.json"])
        assert current["phase"] == "complete", result.stdout + result.stderr
        root_path = "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        assert "automated" not in state["objects"][root_path]["spec"]["syncPolicy"]
        lease_path = "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        state["objects"][lease_path]["spec"]["renewTime"] = "2000-01-01T00:00:00Z"
        state["objects"]["/api/v1/namespaces/selfhosted/pods/coordinator"]["status"][
            "phase"
        ] = "Failed"
        before = deepcopy(state["objects"])
        directory = tmp_path / "watchdog"
        directory.mkdir()
        result = run_role(
            directory,
            "shared_data",
            "maintenance_watchdog",
            {**connection, **variables, **executor},
            timeout=480,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert state["objects"] == before
