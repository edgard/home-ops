"""Run the real bootstrap scheduler with explicit CLI/loopback boundaries."""

import base64
import json
import subprocess
from urllib.parse import urlsplit

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import ROOT, executable, run_role
from tests.support.sources import applications, read_yaml


@pytest.mark.parametrize("failure", ["", "helm", "destroy", "destroy-failure"])
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
        "metadata": {"name": "root", "namespace": "argocd"},
        "spec": {"sources": [{}, {}, {}]},
        "status": {"sync": {"status": "Synced", "revisions": ["a" * 40] * 3}},
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
    allowed.append("/api/v1/namespaces/platform-system/secrets/bitwarden-credentials")
    state = {
        "objects": objects,
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
    executable(
        tmp_path,
        "git",
        """import pathlib,sys
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
if args==['--version']:print('git version fixture')
elif args==['ls-files','--','apps']:print((base/'tracked.txt').read_text())
elif args==['rev-parse','HEAD']:print('a'*40)
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
state['events'].append({'method':'HELM','path':name,'body':args});state_path.write_text(json.dumps(state))
if os.environ.get('HELM_FAIL')==name: print('fixture native Helm failure',file=sys.stderr);sys.exit(93)
if 'uninstall' in args:
 state.setdefault('uninstalled',[]).append(name);state_path.write_text(json.dumps(state))
""",
    )
    with cluster_api(tmp_path, state) as (connection, observed):
        base = urlsplit(
            read_yaml(tmp_path / "kubeconfig")["clusters"][0]["cluster"]["server"]
        )
        result = run_role(
            tmp_path,
            "platform",
            "destroy" if failure.startswith("destroy") else "bootstrap",
            {
                **connection,
                "platform_repository_identity_url": base.geturl() + "/identity",
                "platform_bitwarden_access_token": "synthetic-read-only-token",
                "platform_handoff_timeout": 120,
                "platform_secret_reconcile_timeout": 120,
                "platform_wait_default_delay": 1,
            },
            env={
                "HELM_MODE": "destroy" if failure.startswith("destroy") else "",
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
            timeout=180,
        )
        state = observed()
    assert (result.returncode == 0) == (failure not in ["helm", "destroy-failure"]), (
        result.stdout + result.stderr
    )
    installs = [event["path"] for event in state["events"] if event["method"] == "HELM"]
    if failure.startswith("destroy"):
        assert installs == [
            release["name"]
            for release in reversed(defaults["platform_bootstrap_releases"])
        ]
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
