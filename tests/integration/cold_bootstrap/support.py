"""Synthetic Kubernetes authority; production role modules and Helm rendering stay real."""

import io
import json
import shutil
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from tests.integration import test_data_maintenance as api
from tests.support.runtime import ROOT, executable, load_module, run_role

REVISION = "a" * 40
IMAGE = "ghcr.io/edgard/home-ops-data-tools:" + "a" * 40 + "@sha256:" + "b" * 64


def extend_api(monkeypatch):
    monkeypatch.setitem(
        api.RESOURCES,
        "v1",
        {
            **api.RESOURCES["v1"],
            "Namespace": "namespaces",
            "ServiceAccount": "serviceaccounts",
            "PersistentVolume": "persistentvolumes",
            "PersistentVolumeClaim": "persistentvolumeclaims",
        },
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "rbac.authorization.k8s.io/v1",
        {
            "Role": "roles",
            "RoleBinding": "rolebindings",
            "ClusterRole": "clusterroles",
            "ClusterRoleBinding": "clusterrolebindings",
        },
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "external-secrets.io/v1",
        {
            "ExternalSecret": "externalsecrets",
            "ClusterSecretStore": "clustersecretstores",
        },
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "apiextensions.k8s.io/v1",
        {"CustomResourceDefinition": "customresourcedefinitions"},
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "authentication.k8s.io/v1",
        {"SelfSubjectReview": "selfsubjectreviews"},
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "cert-manager.io/v1",
        {"Issuer": "issuers", "Certificate": "certificates"},
    )
    monkeypatch.setitem(
        api.RESOURCES,
        "k8s.cni.cncf.io/v1",
        {"NetworkAttachmentDefinition": "network-attachment-definitions"},
    )
    servers = []
    server_type = api.HTTPServer
    original_api = api.maintenance_api

    def server(address, handler):
        respond = handler.respond
        post = handler.do_POST
        mutate = handler.mutate

        def corrected(self, value, code=200):
            if value.get("kind") == "APIResourceList":
                for resource in value["resources"]:
                    if resource["kind"] in {
                        "Namespace",
                        "PersistentVolume",
                        "CustomResourceDefinition",
                        "ClusterRole",
                        "ClusterRoleBinding",
                        "SelfSubjectReview",
                        "ClusterSecretStore",
                    }:
                        resource["namespaced"] = False
            return respond(self, value, code)

        def extended_post(self):
            path = urlsplit(self.path).path
            state = self.server.cold_state
            if path == "/apis/authentication.k8s.io/v1/selfsubjectreviews":
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                state["events"].append(
                    {"method": "IDENTITY", "path": path, "body": body}
                )
                user = state.get("token_identities", {}).get(
                    self.headers.get("Authorization"),
                    {"uid": "admin", "username": "fixture-admin", "extra": {}},
                )
                return corrected(
                    self,
                    {
                        "apiVersion": "authentication.k8s.io/v1",
                        "kind": "SelfSubjectReview",
                        "metadata": {},
                        "status": {"userInfo": user},
                    },
                    201,
                )
            if path == "/fixture/helm":
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                lease = state["objects"].get(
                    "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation",
                    {},
                )
                entry = json.loads(
                    lease.get("metadata", {})
                    .get("annotations", {})
                    .get("home-ops/data-coordinator", "{}")
                )
                assert entry.get("actor", {}).get("kind") == "Pod", (
                    "chart mutation without actual Pod authority"
                )
                state["events"].append(
                    {
                        "method": "HELM",
                        "path": body["release"],
                        "body": body,
                        "actor": entry["actor"]["uid"],
                    }
                )
                return corrected(self, {"ok": True})
            return post(self)

        def guarded(self, method):
            state = self.server.cold_state
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            self.rfile = io.BytesIO(raw)
            path = urlsplit(self.path).path
            current = state["objects"].get(path)
            if method == "PATCH" and isinstance(body, dict) and current:
                meta = body.get("metadata", {})
                if (
                    "uid" in meta and meta["uid"] != current["metadata"].get("uid")
                ) or (
                    "resourceVersion" in meta
                    and meta["resourceVersion"]
                    != current["metadata"].get("resourceVersion")
                ):
                    return corrected(
                        self, {"kind": "Status", "reason": "Conflict", "code": 409}, 409
                    )
            return mutate(self, method)

        handler.respond = corrected
        handler.do_POST = extended_post
        handler.mutate = guarded
        instance = server_type(address, handler)
        servers.append(instance)
        return instance

    @contextmanager
    def extended_api(directory, objects):
        with original_api(
            directory, objects, include_default_service_account=False
        ) as (connection, state):
            servers[-1].cold_state = state
            yield connection, state

    monkeypatch.setattr(api, "HTTPServer", server)
    monkeypatch.setattr(api, "maintenance_api", extended_api)


def public_files():
    bundle = load_module("platform/files/cold_bundle.py")
    return {
        str(path.relative_to(ROOT)): path.read_bytes()
        for path in ROOT.rglob("*")
        if path.is_file()
        and (
            bundle.code(str(path.relative_to(ROOT)))
            or bundle.asset(str(path.relative_to(ROOT)))
            or bundle.context_file(str(path.relative_to(ROOT)))
        )
    }


def image_fixture(directory):
    bundle = load_module("platform/files/cold_bundle.py")
    root = directory / "image"
    root.mkdir()
    files = public_files()
    context = bundle.regular_archive(bundle.build_context(files, "f" * 40))
    for name, data in context.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    proof = bundle.image_provenance(root, "f" * 40)
    return root, proof


def git_boundary(directory):
    bundle = load_module("platform/files/cold_bundle.py")
    files = public_files()
    snapshot = directory / "committed.tar"
    snapshot.write_bytes(bundle.archive(files))
    executable(
        directory,
        "git",
        f"""import sys
from pathlib import Path
args=sys.argv[1:]
if args and args[0]=='archive':sys.stdout.buffer.write(Path({str(snapshot)!r}).read_bytes())
elif args==['rev-parse','HEAD']:print({"a" * 40!r})
elif args==['status','--porcelain','--untracked-files=no']:pass
elif args[:1]==['ls-files']:print({chr(10).join(sorted(files))!r})
else:raise SystemExit(94)
""",
    )
    return bundle.source_bundle(files, REVISION)


def infrastructure_objects():
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/platform/defaults/main.yml").read_text()
    )
    objects = []
    for group in [
        "platform_cert_manager_waits",
        "platform_external_secrets_waits",
        "platform_external_secrets_crd_waits",
        "platform_external_secrets_store_waits",
        "platform_argocd_waits",
    ]:
        for row in defaults[group]:
            key = (row["kind"], row["name"], row.get("namespace", ""))
            if any(
                (r["kind"], r["metadata"]["name"], r["metadata"].get("namespace", ""))
                == key
                for r in objects
            ):
                continue
            obj = {
                "apiVersion": row["api_version"],
                "kind": row["kind"],
                "metadata": {
                    "name": row["name"],
                    "uid": "preexisting-" + row["name"],
                    "resourceVersion": "1",
                    **({"namespace": row["namespace"]} if row.get("namespace") else {}),
                },
                "spec": {},
                "status": {
                    "conditions": [{"type": row["condition_type"], "status": "True"}]
                },
            }
            objects.append(obj)
    objects.append(
        {
            "apiVersion": "v1",
            "kind": "Node",
            "metadata": {"name": "node", "uid": "node", "resourceVersion": "1"},
            "status": {"conditions": [{"type": "Ready", "status": "True"}]},
        }
    )
    return objects


def helm_boundary(directory, server, fail_helm=False):
    helm = shutil.which("helm")
    executable(
        directory,
        "helm",
        f"""import json,sys,subprocess,urllib.request
args=sys.argv[1:]
if args[0]=='template':raise SystemExit(subprocess.run([{helm!r}]+args).returncode)
if args[0]=='version':raise SystemExit(subprocess.run([{helm!r}]+args).returncode)
if args[0]=='list':print('[]');raise SystemExit()
if args[0]=='get':print('{{}}');raise SystemExit()
if 'show' in args:print('name: fixture\\nversion: 1.0.0');raise SystemExit()
if args[0]=='plugin':print('NAME VERSION DESCRIPTION');raise SystemExit()
assert 'upgrade' in args,args
release=next(a for a in args if a in ['nfs-provisioner','multus','cert-manager','external-secrets','argocd'])
data=json.dumps({{'release':release,'args':args}}).encode()
request=urllib.request.Request({server!r}+'/fixture/helm',data=data,headers={{'Content-Type':'application/json'}})
with urllib.request.urlopen(request,timeout=10) as response:assert response.status==200
if {fail_helm!r}:raise SystemExit(93)
""",
    )


def start_job_workers(
    tmp_path,
    connection,
    state,
    *,
    failure="",
    admin_worker=False,
    node_claim_failure="",
):
    """Model real Pod scheduling with bound-token API identity; no production override."""
    threads = []
    workers = {}
    started = set()
    counter = [0]
    root, proof = image_fixture(tmp_path)
    bundle_module = load_module("platform/files/cold_bundle.py")

    def created(resource, state):
        resource["metadata"]["uid"] = (
            "created-" + resource["kind"].lower() + "-" + resource["metadata"]["name"]
        )
        if resource["kind"] == "CustomResourceDefinition":
            resource["status"] = {
                "conditions": [{"type": "Established", "status": "True"}]
            }
        if (
            resource["kind"] == "Deployment"
            and resource.get("spec", {}).get("replicas", 1) > 0
        ):
            resource["status"] = {
                "conditions": [{"type": "Available", "status": "True"}]
            }
        if resource["kind"] == "Pod" and resource["metadata"]["name"].startswith(
            "cold-warmup-"
        ):
            resource["status"] = {"phase": "Succeeded"}
        if (
            failure
            and resource["kind"] == "Deployment"
            and resource["metadata"]["name"] == "postgresql"
            and not state.get("injected")
        ):
            foreign = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": "redis",
                    "namespace": "platform-system",
                    "uid": "foreign",
                    "resourceVersion": "1",
                },
                "spec": {"replicas": 0},
            }
            state["objects"][api.path_for(foreign)] = foreign
            state["injected"] = True

    def patched(path, resource, state):
        if (
            resource["kind"] == "Deployment"
            and resource.get("spec", {}).get("replicas", 1) > 0
        ):
            resource.setdefault("status", {})["conditions"] = [
                {"type": "Available", "status": "True"}
            ]
        if (
            resource["kind"] != "Job"
            or resource["spec"].get("suspend")
            or resource["metadata"]["uid"] in started
        ):
            return
        started.add(resource["metadata"]["uid"])
        counter[0] += 1
        number = counter[0]
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": resource["metadata"]["name"] + "-pod",
                "namespace": resource["metadata"]["namespace"],
                "uid": "pod-" + resource["metadata"]["uid"],
                "resourceVersion": "1",
                "ownerReferences": [
                    {
                        "kind": "Job",
                        "name": resource["metadata"]["name"],
                        "uid": resource["metadata"]["uid"],
                        "controller": True,
                    }
                ],
            },
            "spec": deepcopy(resource["spec"]["template"]["spec"]),
            "status": {"phase": "Running"},
        }
        pod["spec"]["nodeName"] = "node"
        state["objects"][api.path_for(pod)] = pod
        sa = state["objects"][
            "/api/v1/namespaces/platform-system/serviceaccounts/"
            + resource["metadata"]["name"]
        ]
        token = "pod:" + pod["metadata"]["uid"]
        node_path = "/api/v1/nodes/" + pod["spec"]["nodeName"]
        node = state["objects"][node_path]
        claims = {
            "authentication.kubernetes.io/pod-uid": [pod["metadata"]["uid"]],
            "authentication.kubernetes.io/node-name": [node["metadata"]["name"]],
            "authentication.kubernetes.io/node-uid": [node["metadata"]["uid"]],
        }
        if node_claim_failure == "replacement":
            replacement = deepcopy(node)
            replacement["metadata"]["uid"] = "replacement-node"
            replacement["metadata"]["resourceVersion"] = "2"
            state["objects"][node_path] = replacement
        elif node_claim_failure == "name":
            claims["authentication.kubernetes.io/node-name"] = ["other-node"]
        elif node_claim_failure == "missing":
            claims.pop("authentication.kubernetes.io/node-name")
            claims.pop("authentication.kubernetes.io/node-uid")
        state.setdefault("token_identities", {})["Bearer " + token] = {
            "uid": sa["metadata"]["uid"],
            "username": "system:serviceaccount:platform-system:"
            + sa["metadata"]["name"],
            "extra": claims,
        }
        directory = tmp_path / ("worker-" + str(number))
        directory.mkdir()
        config = yaml.safe_load(Path(connection["kubeconfig_path"]).read_text())
        config["users"][0]["user"] = {
            "token": "operator-admin" if admin_worker else token
        }
        kube = directory / "kubeconfig"
        kube.write_text(yaml.safe_dump(config))
        ctx = state["objects"][
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-cold-recovery"
        ]
        state.setdefault("worker_start_journals", {})[pod["metadata"]["uid"]] = ctx[
            "data"
        ]["journal.json"]
        state.setdefault("worker_start_events", {})[pod["metadata"]["uid"]] = len(
            state["events"]
        )
        journal = json.loads(ctx["data"]["journal.json"])
        assets = state["objects"][
            "/api/v1/namespaces/platform-system/configmaps/"
            + resource["metadata"]["name"]
        ]
        extracted = directory / "source"
        extracted.mkdir(mode=0o700)
        raw = __import__("base64").b64decode(assets["binaryData"]["bundle.tar.gz"])
        bundle_module.unpack(
            raw,
            extracted,
            journal["revision"],
            journal["executor"]["bundle_sha256"],
            journal["source_sha256"],
        )
        server = config["clusters"][0]["cluster"]["server"]
        helm_boundary(directory, server, failure == "helm")
        params = {
            "kubeconfig_path": str(kube),
            "kube_context": "fixture",
            "repo_root": str(extracted),
            "platform_recovery_worker": True,
            "platform_recovery_mode": True,
            "platform_bootstrap_revision": journal["revision"],
            "platform_recovery_apps": journal["apps"],
            "platform_recovery_operation": journal["operation"],
            "platform_recovery_image": journal["executor"]["image"],
            "platform_recovery_code_sha256": journal["executor"]["code_sha256"],
            "platform_recovery_bundle_sha256": journal["executor"]["bundle_sha256"],
            "platform_recovery_job_name": resource["metadata"]["name"],
            "platform_recovery_pod_name": pod["metadata"]["name"],
            "platform_recovery_pod_uid": pod["metadata"]["uid"],
            "platform_recovery_image_root": str(root),
            "platform_bitwarden_access_token": "synthetic-only",
            "platform_wait_default_delay": 1,
            "platform_wait_retries": 1,
            "platform_wait_delay": 1,
        }

        def run():
            try:
                result = run_role(
                    directory, "platform", "recovery_worker", params, timeout=1800
                )
                (directory / "result.log").write_text(result.stdout + result.stderr)
                workers[resource["metadata"]["uid"]] = result
                resource["status"] = (
                    {"succeeded": 1} if result.returncode == 0 else {"failed": 1}
                )
                pod["status"] = {
                    "phase": "Succeeded" if result.returncode == 0 else "Failed"
                }
            except BaseException as error:
                workers[resource["metadata"]["uid"]] = error
                resource["status"] = {"failed": 1}
                pod["status"] = {"phase": "Failed"}

        thread = threading.Thread(target=run, daemon=True)
        threads.append(thread)
        thread.start()

    state["created"] = created
    state["patched"] = patched
    return threads, workers
