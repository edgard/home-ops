"""Run the real bootstrap scheduler with explicit CLI/loopback boundaries."""

import base64
import json
import subprocess
from urllib.parse import urlsplit

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import ROOT, executable, run_role
from tests.support.sources import applications, read_yaml


@pytest.mark.parametrize(
    "failure",
    [
        "",
        "helm",
        "handoff-failure",
        "destroy",
        "destroy-failure",
        "destroy-namespace-loss",
        "destroy-foreign-root",
        "destroy-nondeleting-root",
        "destroy-changed-revision",
        "destroy-foreign-source",
        "destroy-unrelated-drift",
        "fresh-composed",
        "fresh-root-get-race",
        "fresh-root-post-race",
    ],
)
def test_bootstrap_order_and_native_failure(tmp_path, provider, failure):
    _, values, targets, manifests = provider
    credentials = {row["key"]: row["value"] for row in values}
    defaults = read_yaml(ROOT / "ansible/roles/platform/defaults/main.yml")
    objects = {}
    plurals = {
        "Deployment": "deployments",
        "Application": "applications",
        "ApplicationSet": "applicationsets",
        "ExternalSecret": "externalsecrets",
        "ClusterSecretStore": "clustersecretstores",
        "Certificate": "certificates",
        "CustomResourceDefinition": "customresourcedefinitions",
        "Secret": "secrets",
    }

    def key(version, kind, namespace, name):
        prefix = "/api/" + version if "/" not in version else "/apis/" + version
        return (
            prefix
            + ("/namespaces/" + namespace if namespace else "")
            + "/"
            + plurals[kind]
            + "/"
            + name
        )

    for group in [
        "platform_cert_manager_waits",
        "platform_external_secrets_waits",
        "platform_external_secrets_crd_waits",
        "platform_external_secrets_store_waits",
        "platform_argocd_waits",
    ]:
        for item in defaults[group]:
            version, kind, namespace, name = (
                item["api_version"],
                item["kind"],
                item.get("namespace", ""),
                item["name"],
            )
            objects[key(version, kind, namespace, name)] = {
                "apiVersion": version,
                "kind": kind,
                "metadata": {
                    "name": name,
                    **({"namespace": namespace} if namespace else {}),
                },
                "spec": {},
                "status": {
                    "conditions": [{"type": item["condition_type"], "status": "True"}]
                },
            }
    root = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {
            "name": "root",
            "namespace": "argocd",
            "uid": "root-uid",
            "resourceVersion": "1",
        },
        "spec": {"sources": [{}, {}, {}]},
        "status": {
            "sync": {"status": "Synced", "revisions": ["a" * 40] * 3},
            "operationState": {
                "phase": "Succeeded",
                "finishedAt": "2000-01-01T00:00:00Z",
                "syncResult": {"revisions": ["a" * 40] * 3},
            },
        },
    }
    objects[key("argoproj.io/v1alpha1", "Application", "argocd", "root")] = root
    objects[key("argoproj.io/v1alpha1", "ApplicationSet", "argocd", "apps")] = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "ApplicationSet",
        "metadata": {"name": "apps", "namespace": "argocd", "uid": "fixture-owner"},
        "spec": {},
    }
    for app in applications(ROOT):
        objects[key("argoproj.io/v1alpha1", "Application", "argocd", app.name)] = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Application",
            "metadata": {
                "name": app.name,
                "namespace": "argocd",
                "ownerReferences": [{"uid": "fixture-owner"}],
            },
            "spec": {},
        }
    for current in objects.values():
        current["metadata"].setdefault("uid", current["metadata"]["name"] + "-uid")
        current["metadata"].setdefault("resourceVersion", "1")
    for manifest in manifests:
        namespace = manifest["metadata"]["namespace"]
        name = manifest["metadata"]["name"]
        objects[key("external-secrets.io/v1", "ExternalSecret", namespace, name)] = {
            **manifest,
            "status": {
                "refreshTime": "2100-01-01T00:00:00Z",
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        }
        name = manifest["spec"]["target"]["name"]
        objects[key("v1", "Secret", namespace, name)] = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": namespace},
            "data": targets,
        }
    objects["/api/v1/nodes/node"] = {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {"name": "node", "uid": "node-uid", "resourceVersion": "1"},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }
    if failure.startswith("fresh-"):
        objects["/api/v1/nodes/node"]["status"]["addresses"] = [
            {"type": "InternalIP", "address": "192.0.2.10"}
        ]
    objects["/api/v1/namespaces/selfhosted"] = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {
            "name": "selfhosted",
            "uid": "selfhosted-uid",
            "resourceVersion": "1",
            "annotations": {"argocd.argoproj.io/sync-options": "Delete=false"},
        },
    }
    allowed = (
        list(objects)
        + [
            "/api/v1/namespaces/" + namespace
            for namespace in defaults["platform_bootstrap_namespaces"]
        ]
        + [
            "/api/v1/namespaces/kube-system/pods/"
            + defaults["platform_k8tz_warmup_pod_name"]
        ]
    )
    owned = [
        ROOT / path
        for path in defaults["platform_external_secrets_bootstrap_manifests"]
    ] + [
        path
        for release in defaults["platform_bootstrap_releases"]
        if release.get("manifests_dir")
        for path in (ROOT / release["manifests_dir"]).glob("*.yaml")
    ]
    resources = {
        "PersistentVolume": "persistentvolumes",
        "PersistentVolumeClaim": "persistentvolumeclaims",
        "NetworkAttachmentDefinition": "network-attachment-definitions",
        "Issuer": "issuers",
        "Certificate": "certificates",
        "Secret": "secrets",
    }
    for path in owned:
        for doc in read_yaml(path, multiple=True):
            version = doc["apiVersion"]
            prefix = "/api/" + version if "/" not in version else "/apis/" + version
            namespace = doc["metadata"].get("namespace", "")
            allowed.append(
                prefix
                + ("/namespaces/" + namespace if namespace else "")
                + "/"
                + resources[doc["kind"]]
                + "/"
                + doc["metadata"]["name"]
            )
    allowed += [
        "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation",
        "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation",
    ]
    allowed.append("/api/v1/namespaces/platform-system/secrets/bitwarden-credentials")
    state = {
        "objects": objects,
        "model_root_cascade": True,
        "model_owned_fence_drift": failure.startswith("destroy"),
        "retention_drift": failure,
        "fail_native_handoff": failure == "handoff-failure",
        "destroy_application_race": failure
        if failure in {"destroy-foreign-root", "destroy-nondeleting-root"}
        else "",
        "events": [],
        "allowed_creates": allowed,
        "identity_authorization": "Basic "
        + base64.b64encode(
            (
                credentials["argocd_repo_username"]
                + ":"
                + credentials["argocd_repo_password"]
            ).encode()
        ).decode(),
    }
    if failure.startswith("fresh-"):
        state["fresh_api_pending"] = True
        generated = {
            path: objects.pop(path)
            for path in list(objects)
            if "/applications/" in path or "/applicationsets/" in path
        }
        state["fresh_root_status"] = generated.pop(
            key("argoproj.io/v1alpha1", "Application", "argocd", "root")
        )["status"]
        state["fresh_generated_objects"] = generated
        if failure in {"fresh-root-get-race", "fresh-root-post-race"}:
            state["root_creation_race"] = "get" if "get" in failure else "post"
            state["foreign_root"] = {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Application",
                "metadata": {
                    "name": "root",
                    "namespace": "argocd",
                    "uid": "foreign-root",
                    "resourceVersion": "99",
                },
                "spec": {
                    "source": {"targetRevision": "foreign"},
                    "syncPolicy": {"automated": {"selfHeal": True}},
                },
            }
    pin = read_yaml(ROOT / "ansible/roles/cli_secrets/defaults/main.yml")[
        "cli_secrets_secretspec_version"
    ]
    executable(
        tmp_path,
        "secretspec",
        "print('secretspec " + pin + "')\n",
    )
    # Provider list/read fixture remains active; add only the normal version command it needs.
    bws = tmp_path / "bws"
    bws.write_text(
        bws.read_text().replace(
            "args=sys.argv[1:]",
            "args=sys.argv[1:]\nif args==['--version']: print('bws 2.1.0');sys.exit()",
        )
    )
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", "apps"], cwd=ROOT, text=True
    )
    (tmp_path / "tracked.txt").write_text(tracked)
    (tmp_path / "releases.json").write_text(
        json.dumps(defaults["platform_bootstrap_releases"])
    )
    (tmp_path / "retained-namespace.yaml").write_text(
        (ROOT / "argocd/namespaces/selfhosted.namespace.yaml").read_text()
    )
    (tmp_path / "root-source.yaml").write_text(
        (ROOT / "argocd/root.app.yaml").read_text()
    )
    executable(
        tmp_path,
        "git",
        """import pathlib,sys
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
if args==['--version']:print('git version fixture')
elif args==['ls-files','--','apps']:print((base/'tracked.txt').read_text())
elif args==['rev-parse','HEAD']:print('a'*40)
elif 'show' in args and args[-1]=='a'*40+':argocd/root.app.yaml':print((base/'root-source.yaml').read_text())
elif 'show' in args and args[-1]=='a'*40+':argocd/namespaces/selfhosted.namespace.yaml':print((base/'retained-namespace.yaml').read_text())
elif args==['status','--porcelain','--untracked-files=no']:pass
elif 'ls-remote' in args:
 import os
 assert os.environ['GIT_TERMINAL_PROMPT']=='0' and os.environ['GIT_CONFIG_COUNT']=='0'
 assert pathlib.Path(os.environ['GIT_ASKPASS']).stat().st_mode&0o777==0o700
 print('a'*40+'\\trefs/heads/master')
else:sys.exit(94)
""",
    )
    executable(
        tmp_path,
        "talosctl",
        "import sys\nassert sys.argv[1:]==['version','--client','--short']\nprint('fixture')\n",
    )
    if failure.startswith("fresh-"):
        executable(
            tmp_path,
            "talosctl",
            """import json,pathlib,sys,yaml
base=pathlib.Path(__file__).parent;args=sys.argv[1:]
node='192.0.2.10'
with (base/'fresh-native.jsonl').open('a') as log:log.write(json.dumps(args)+'\\n')
if 'get' in args:
 name=args[args.index('get')+1]
 spec={'stage':'maintenance'} if name=='machinestatus' else {'dev_path':'/dev/fixture','type':'disk','size':1000000}
 print(yaml.safe_dump_all([{'node':node,'metadata':{'id':'fixture'},'spec':spec}]))
elif 'bootstrap' in args:
 state_path=base/'api-state.json';state=json.loads(state_path.read_text());state['fresh_api_pending']=False;state_path.write_text(json.dumps(state))
elif 'version' in args:print('fixture')
elif any(action in args for action in ['apply-config','health','kubeconfig','config']):pass
else:raise AssertionError(args)
""",
        )
    executable(
        tmp_path,
        "helm",
        """import json,os,pathlib,sys
args=sys.argv[1:];base=pathlib.Path(__file__).parent
if args[0]=='version':print('version.BuildInfo{Version:"v4.0.0",}');sys.exit()
if args[0]=='list':
 name=args[args.index('--filter')+1]
 state=json.loads((base/'api-state.json').read_text())
 print(json.dumps([{'name':name,'status':'deployed','chart':'fixture-1.0.0','app_version':'1.0.0'}]) if os.environ.get('HELM_MODE')=='destroy' and name not in state.get('uninstalled',[]) else '[]');sys.exit()
if args[0]=='get':assert args[1]=='values';print('{}');sys.exit()
if 'show' in args:print('name: fixture\\nversion: 1.0.0');sys.exit()
if args[0]=='plugin':print('NAME VERSION DESCRIPTION');sys.exit()
assert 'upgrade' in args or 'uninstall' in args,args
releases=json.loads((base/'releases.json').read_text())
name=next((a for a in args if a in {release['name'] for release in releases}),None)
assert name,args
state_path=base/'api-state.json';state=json.loads(state_path.read_text())
assert state['objects']['/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation']['spec']['holderIdentity'].startswith('native-')
state['events'].append({'method':'HELM','path':name,'body':args});state_path.write_text(json.dumps(state))
if os.environ.get('HELM_FAIL')==name: print('fixture native Helm failure',file=sys.stderr);sys.exit(93)
if 'uninstall' in args:
 state.setdefault('uninstalled',[]).append(name)
 if os.environ.get('DESTROY_LOSE_NAMESPACE'):
  state['objects']['/api/v1/namespaces/selfhosted']['metadata']['deletionTimestamp']='2026-01-01T00:00:00Z'
  for key,value in list(state['objects'].items()):
   if '/namespaces/selfhosted/' in key:
    if value['metadata'].get('finalizers'):value['metadata']['deletionTimestamp']='2026-01-01T00:00:00Z'
    else:del state['objects'][key]
 state_path.write_text(json.dumps(state))
""",
    )
    with cluster_api(tmp_path, state) as (connection, observed):
        base = urlsplit(
            read_yaml(tmp_path / "kubeconfig")["clusters"][0]["cluster"]["server"]
        )
        result = run_role(
            tmp_path,
            "platform",
            "destroy"
            if failure.startswith("destroy")
            else "preflight"
            if failure.startswith("fresh-")
            else "bootstrap",
            {
                **connection,
                "platform_repository_identity_url": base.geturl() + "/identity",
                "platform_bitwarden_access_token": "synthetic-read-only-token",
                "platform_handoff_timeout": 1 if failure == "handoff-failure" else 120,
                "platform_secret_reconcile_timeout": 120,
                "platform_wait_default_delay": 1,
                "node_operation_ready_retries": 1,
                "node_operation_ready_delay": 0,
                "node_operation_action": "cluster-create",
                "node_operation_fresh": failure.startswith("fresh-"),
                "talos_node": "192.0.2.10" if failure.startswith("fresh-") else "",
                "talos_cluster_name": "fixture",
                "talos_install_disk": "/dev/fixture",
                "talos_config_path": str(tmp_path / "synthetic-talosconfig"),
                "talos_controlplane_config_path": str(
                    tmp_path / "synthetic-controlplane"
                ),
            },
            env={
                "HELM_MODE": "destroy" if failure.startswith("destroy") else "",
                "DESTROY_LOSE_NAMESPACE": "1"
                if failure == "destroy-namespace-loss"
                else "",
                "HELM_FAIL": (
                    next(
                        release["name"]
                        for release in defaults["platform_bootstrap_releases"]
                        if release["phase"]
                        == (
                            "argocd" if failure == "destroy-failure" else "certificates"
                        )
                    )
                    if failure in ["helm", "destroy-failure"]
                    else ""
                ),
            },
            after=[
                {
                    "ansible.builtin.include_role": {
                        "name": "node_operation",
                        "tasks_from": "main",
                    }
                }
            ]
            if failure.startswith("fresh-")
            else None,
            timeout=360,
        )
        state = observed()
        (tmp_path / "role-output.log").write_text(result.stdout + result.stderr)
    assert (result.returncode == 0) == (
        failure
        not in [
            "helm",
            "handoff-failure",
            "destroy-failure",
            "destroy-namespace-loss",
            "fresh-root-get-race",
            "fresh-root-post-race",
            "destroy-foreign-root",
            "destroy-nondeleting-root",
            "destroy-changed-revision",
            "destroy-foreign-source",
            "destroy-unrelated-drift",
        ]
    ), result.stdout + result.stderr
    if failure == "handoff-failure":
        root = state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        ]
        assert (
            root["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"]
            == "true"
        )
        assert state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
        record = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert record["phase"] == "native-critical-complete"
    if failure in {"fresh-root-get-race", "fresh-root-post-race"}:
        assert (
            state["objects"][
                "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
            ]
            == state["foreign_root"]
        )
        assert state["root_creation_race"] == "injected"
        if failure == "fresh-root-get-race":
            assert state["root_missing_rv_put_rejected"]
        assert state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
    elif failure == "fresh-composed":
        assert state["fresh_handoff_after_critical_completion"]
        calls = [
            json.loads(row)
            for row in (tmp_path / "fresh-native.jsonl").read_text().splitlines()
        ]
        assert any("apply-config" in args for args in calls)
        assert any("bootstrap" in args for args in calls)
        assert (
            state["objects"][
                "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
            ]["spec"]["holderIdentity"]
            == ""
        )
    installs = [event["path"] for event in state["events"] if event["method"] == "HELM"]
    if failure in {
        "destroy-changed-revision",
        "destroy-foreign-source",
        "destroy-unrelated-drift",
    }:
        assert not installs
        assert not any(event["method"] == "DELETE" for event in state["events"])
        assert state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
    elif failure in {"destroy-foreign-root", "destroy-nondeleting-root"}:
        assert not installs
        root_after = state["objects"][
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root"
        ]
        assert (
            root_after["metadata"]["annotations"]["argocd.argoproj.io/skip-reconcile"]
            == "true"
        )
        if failure == "destroy-foreign-root":
            assert root_after == state["foreign_deleting_root"]
        assert state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
    elif failure.startswith("destroy"):
        expected = [
            release["name"]
            for release in reversed(defaults["platform_bootstrap_releases"])
        ]
        assert installs == (
            expected[:1]
            if failure in {"destroy-failure", "destroy-namespace-loss"}
            else expected
        )
        assert state["root_owned_fence_status_refresh"] is True
        assert state["root_cascade_retained_namespace"] is True
        assert state["root_finalizer_stalled_on_skip"] is True
        assert state["tuppr_finalizer_stalled_on_skip"] is True
        assert state["root_finalizer_completed"] is True
        assert "/api/v1/namespaces/selfhosted" in state["objects"]
        assert (
            "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            in state["objects"]
        )
        holder = state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
        assert bool(holder) == (
            failure in {"destroy-failure", "destroy-namespace-loss"}
        )
        if failure == "destroy-namespace-loss":
            for key in [
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation",
                "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation",
            ]:
                assert state["objects"][key]["metadata"]["finalizers"] == [
                    "home-ops/native-operation"
                ]
                assert state["objects"][key]["metadata"]["deletionTimestamp"]
        assert all(
            "--wait" in event["body"] and "--timeout" in event["body"]
            for event in state["events"]
            if event["method"] == "HELM"
        )
        assert any(
            event["method"] == "DELETE" and event["path"].endswith("/applications/root")
            for event in state["events"]
        )
    else:
        phase_order = [
            "storage",
            "networking",
            "certificates",
            "external-secrets",
            "argocd",
        ]
        expected = [
            release["name"]
            for phase in phase_order
            for release in defaults["platform_bootstrap_releases"]
            if release["phase"] == phase
        ]
        assert installs == (expected[:3] if failure == "helm" else expected)
        if not failure:
            token_writes = [
                event
                for event in state["events"]
                if event["method"] in ["POST", "PATCH"]
                and isinstance(event["body"], dict)
                and event["body"].get("kind") == "Secret"
                and "token" in event["body"].get("stringData", {})
            ]
            assert len(token_writes) == 1
            write = token_writes[0]
            assert write["path"] == "/api/v1/namespaces/platform-system/secrets" + (
                "/bitwarden-credentials" if write["method"] == "PATCH" else ""
            )
            assert write["body"]["metadata"]["name"] == "bitwarden-credentials"
            assert write["body"]["metadata"]["namespace"] == "platform-system"
            assert write["body"]["stringData"] == {"token": "synthetic-read-only-token"}
        auth = next(
            i for i, event in enumerate(state["events"]) if event["method"] == "AUTH"
        )
        assert auth < next(
            i
            for i, event in enumerate(state["events"])
            if event["method"] not in ["GET", "AUTH"]
        )
        assert "synthetic-read-only-token" not in result.stdout + result.stderr
        assert "SYNTHETIC-PRIVATE" not in result.stdout + result.stderr
