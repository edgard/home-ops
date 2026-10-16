import base64
import json
import pytest
from tests.support.runtime import ROOT, executable
from tests.support.sources import applications, read_toml, read_yaml


@pytest.fixture
def provider(tmp_path):
    config = read_toml(ROOT / "secretspec.toml")
    projects = [{"id": item["uri"].split("/")[-1]} for item in config["providers"].values()]
    manifests = [
        doc
        for app in applications(ROOT)
        for doc in app.documents
        if doc.get("kind") == "ExternalSecret"
    ]
    values = [
        {"id": key, "key": key, "value": "SYNTHETIC-PRIVATE-" + key}
        for key in sorted(
            {entry["remoteRef"]["key"] for doc in manifests for entry in doc["spec"]["data"]}
        )
    ]
    targets = {
        entry["secretKey"]: base64.b64encode(b"synthetic").decode()
        for doc in manifests
        for entry in doc["spec"]["data"]
    }
    targets.update(
        {
            key: base64.b64encode(b"synthetic").decode()
            for doc in manifests
            for key in doc["spec"]["target"].get("template", {}).get("data", {})
        }
    )
    for name, rows in [("projects", projects), ("secrets", values)]:
        (tmp_path / (name + ".json")).write_text(json.dumps(rows))
    (tmp_path / "bitwarden-project").write_text(
        read_yaml(ROOT / "apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml")["spec"]["provider"]["bitwardensecretsmanager"]["projectID"]
    )
    executable(
        tmp_path,
        "bws",
        """import pathlib,sys,os
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
assert os.environ['BWS_ACCESS_TOKEN']=='synthetic-read-only-token'
assert os.environ.get('BW_ACCESS_TOKEN','')==''
if args == ['--color','no','--server-url','https://vault.bitwarden.com','project','list','--output','json']:
 print((base/'projects.json').read_text())
elif len(args)==9 and args[6]==(base/'bitwarden-project').read_text() and args[:6]==['--color','no','--server-url','https://vault.bitwarden.com','secret','list'] and args[7:]==['--output','json']:
 print((base/'secrets.json').read_text())
else: sys.exit(92)
""",
    )
    return projects, values, targets, manifests


@pytest.fixture
def secret_api(provider):
    _, _, _, manifests = provider
    holder = "/api/v1/namespaces/platform-system/secrets/bitwarden-credentials"
    paths = {holder, "/apis/external-secrets.io/v1/clustersecretstores/external-secrets-store"}
    for manifest in manifests:
        namespace = manifest["metadata"]["namespace"]
        paths.add(
            f"/apis/external-secrets.io/v1/namespaces/{namespace}/externalsecrets/{manifest['metadata']['name']}"
        )
        paths.add(f"/api/v1/namespaces/{namespace}/secrets/{manifest['spec']['target']['name']}")
    paths.update(
        {
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications/root",
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applicationsets/apps",
            "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications",
        }
    )
    return {"allowed_reads": sorted(paths), "credential_path": holder, "patch_paths": []}
