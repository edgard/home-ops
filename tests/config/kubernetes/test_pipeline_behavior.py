import json
import subprocess

import pytest
import yaml

from tests.support.runtime import executable, run_role, environment
from tests.support.sources import read_yaml


@pytest.mark.parametrize("failure", ["", "helm", "schema", "pluto"])
def test_native_pipeline_keeps_crds_schema_precedence_and_failure(tmp_path, failure):
    root = tmp_path / "repo with spaces"
    app = root / "apps/platform-system/tuppr"
    (app / "manifests").mkdir(parents=True)
    (root / "argocd").mkdir()
    (app / "app.yaml").write_text("---\nchart:\n  repo: oci://example/chart\n  version: 1.0.0\n")
    (app / "values.yaml").write_text("---\nfixture: true\n")
    (app / "manifests/tuppr-kubernetes.kubernetesupgrade.yaml").write_text(
        "---\napiVersion: fixture.io/v1\nkind: Demo\nmetadata:\n  name: demo\nspec:\n  kubernetes:\n    version: v1.36.1\n"
    )
    crd = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "demos.fixture.io"},
        "spec": {
            "group": "fixture.io",
            "names": {"kind": "Demo", "plural": "demos"},
            "scope": "Namespaced",
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "storage": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "kubernetes": {
                                            "type": "object",
                                            "properties": {"version": {"type": "string"}},
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            ],
        },
    }
    crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"].update(
        apiVersion={"type": "string"},
        kind={"type": "string"},
        metadata={"type": "object", "x-kubernetes-preserve-unknown-fields": True},
    )
    (tmp_path / "chart.yaml").write_text(yaml.safe_dump(crd))
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    for name in ["helm", "kubeconform", "pluto"]:
        executable(
            tmp_path,
            name,
            """import json,os,pathlib,sys
base=pathlib.Path(__file__).parent
args=sys.argv[1:];name=pathlib.Path(sys.argv[0]).name
with (base/'tools.jsonl').open('a') as f:f.write(json.dumps({'name':name,'args':args,'env':{k:v for k,v in os.environ.items() if k.startswith('HELM_')}})+'\\n')
assert (name=='helm' and args[0] in ['pull','template']) or (name=='kubeconform' and args[0]=='-kubernetes-version') or (name=='pluto' and args[0]=='detect-files'),args
if name==os.environ.get('FAIL') or (name=='kubeconform' and os.environ.get('FAIL')=='schema'):sys.exit(93)
if name=='helm' and args[0]=='pull':(pathlib.Path(args[args.index('--untardir')+1])/'chart').mkdir()
if name=='helm' and args[0]=='template':
 assert '--include-crds' in args
 print((base/'chart.yaml').read_text())
if name=='kubeconform':
 assert '-ignore-missing-schemas' not in args
 local=pathlib.Path(args[args.index('-schema-location')+1].split('{{')[0])
 assert (local/'fixture.io/demo_v1.json').exists(), 'CRDs must be exported before schema validation'
""",
        )
    result = run_role(
        tmp_path,
        "kubernetes_validation",
        "main",
        {
            "kubernetes_validation_repo_root": str(root),
            "kubernetes_validation_output_dir": str(output),
        },
        env={"FAIL": failure},
    )
    assert (result.returncode == 0) == (not failure), result.stdout + result.stderr
    assert output.is_dir(), "caller owns workspace cleanup"
    events = [json.loads(line) for line in (tmp_path / "tools.jsonl").read_text().splitlines()]
    if not failure:
        assert (output / "rendered/platform-system/tuppr.yaml").is_file()
        schema_commands = [event["args"] for event in events if event["name"] == "kubeconform"]
        assert len(schema_commands) == 2
        for args in schema_commands:
            locations = [args[i + 1] for i, item in enumerate(args) if item == "-schema-location"]
            assert (
                locations[0].startswith(str(output / "schemas"))
                and locations[1] == "default"
                and "CRDs-catalog" in locations[2]
            )
        rendered = read_yaml(output / "rendered/platform-system/tuppr.yaml")
        assert rendered["kind"] == "CustomResourceDefinition"
        assert all(
            value.startswith(str(output))
            for event in events
            if event["name"] == "helm"
            for value in event["env"].values()
        )
        # The real validator must use the served schema and fail closed on unknown/missing schemas.
        resource = app / "manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
        native = [
            "kubeconform",
            "-schema-location",
            str(output / "schemas") + "/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json",
            str(resource),
        ]
        # Deliberately exclude the temporary fake executable from PATH for this separate native boundary.
        import os

        env = environment(tmp_path)
        env["PATH"] = os.environ["PATH"]
        valid = subprocess.run(native, env=env, capture_output=True, text=True, timeout=30)
        assert valid.returncode == 0, valid.stdout + valid.stderr
        document = read_yaml(resource)
        document["spec"]["unknown"] = "forbidden"
        resource.write_text(yaml.safe_dump(document))
        invalid = subprocess.run(native, env=env, capture_output=True, text=True, timeout=30)
        assert invalid.returncode != 0, invalid.stdout + invalid.stderr
        document["kind"] = "MissingSchema"
        resource.write_text(yaml.safe_dump(document))
        missing = subprocess.run(native, env=env, capture_output=True, text=True, timeout=30)
        assert missing.returncode != 0, missing.stdout + missing.stderr
