import json
import stat
from pathlib import Path

import pytest

from tests.support.api import cluster_api
from tests.support.runtime import ROOT, executable, run_role
from tests.support.sources import read_yaml

from tests.support.talos import MATERIAL


@pytest.fixture
def talos(tmp_path):
    defaults = read_yaml(ROOT / "ansible/roles/talos/defaults/main.yml")
    variables = {
        "k8s_version": read_yaml(
            ROOT / "apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
        )["spec"]["kubernetes"]["version"],
        "talos_node": "192.0.2.10",
        "talos_cluster_name": "fixture",
        "talos_install_disk": "/dev/fixture",
        "talos_config_path": str(tmp_path / "custom client/config"),
        "talos_controlplane_config_path": str(tmp_path / "custom machine/controlplane.yaml"),
        "talos_api_wait_retries": 1,
        "talos_api_wait_delay": 0,
        "talos_health_wait_timeout": "1s",
        "talos_secrets_yaml": MATERIAL,
        "kubeconfig_path": str(tmp_path / "client/kubeconfig"),
        "kube_context": "fixture",
    }
    executable(
        tmp_path,
        "talosctl",
        """import json,os,pathlib,stat,sys
args=sys.argv[1:]
base=pathlib.Path(__file__).parent
with (base/'commands.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
allowed=('config','version','apply-config','bootstrap','health','kubeconfig','reset','upgrade','upgrade-k8s','validate','gen')
assert any(item in args for item in allowed), args
if 'gen' in args:
 source=pathlib.Path(args[args.index('--with-secrets')+1])
 assert stat.S_IMODE(source.stat().st_mode)==0o600
 output=pathlib.Path(args[args.index('--output-dir')+1])
 (base/'private-paths.json').write_text(json.dumps([str(source),str(output)]))
 if os.environ.get('FAIL')=='gen':
  print('PRIVATE_FAILURE_MATERIAL',file=sys.stderr);sys.exit(1)
 (output/'talosconfig').write_text('synthetic-config')
 (output/'controlplane.yaml').write_text('synthetic-controlplane')
elif 'version' in args:
 print(json.dumps({'version':{'tag':os.environ.get('SERVER_VERSION')},'client':{'tag':'v99.9.9'}}) if '--json' in args else 'synthetic-version')
elif 'kubeconfig' in args:
 pathlib.Path(args[args.index('kubeconfig')+1]).write_text('synthetic-kubeconfig')
if os.environ.get('FAIL') in args:
 print('PRIVATE_FAILURE_MATERIAL',file=sys.stderr);sys.exit(1)
""",
    )

    def commands():
        path = tmp_path / "commands.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    return variables, defaults, commands


@pytest.mark.parametrize("failure", ["", "gen", "validate", "material"])
def test_generation_private_files_cleanup_and_targets(tmp_path, talos, failure):
    variables, defaults, commands = talos
    if failure == "material":
        variables["talos_secrets_yaml"] = "!PRIVATE_FAILURE_MATERIAL"
    result = run_role(tmp_path, "talos", "generate", variables, env={"FAIL": failure})
    assert (result.returncode == 0) == (failure == ""), result.stdout + result.stderr
    assert "PRIVATE_FAILURE_MATERIAL" not in result.stdout + result.stderr
    if failure == "material":
        assert not commands()
        return
    if failure in ["", "validate"]:
        args = commands()[1]
        assert args[0] == "validate" and args[args.index("--mode") + 1] == "metal"
        output = json.loads((tmp_path / "private-paths.json").read_text())[1]
        assert args[args.index("--config") + 1] == str(Path(output) / "controlplane.yaml")
    for path in json.loads((tmp_path / "private-paths.json").read_text()):
        assert not Path(path).exists()
    config = Path(variables["talos_config_path"])
    plane = Path(variables["talos_controlplane_config_path"])
    assert config.exists() == plane.exists() == (failure == "")
    if not failure:
        assert stat.S_IMODE(config.stat().st_mode) == stat.S_IMODE(plane.stat().st_mode) == 0o600
        assert stat.S_IMODE(config.parent.stat().st_mode) == 0o700
        args = commands()[0]
        upgrade = read_yaml(
            ROOT / "apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
        )
        installer = defaults["talos_upgrade"]["installer"]
        for flag, value in [
            ("--talos-version", installer["version"]),
            ("--kubernetes-version", upgrade["spec"]["kubernetes"]["version"]),
            ("--install-image", installer["repository"] + ":" + installer["version"]),
        ]:
            assert args[args.index(flag) + 1] == value


@pytest.mark.parametrize(
    "entry", ["generate", "apply", "bootstrap", "reset", "upgrade", "upgrade_k8s"]
)
def test_every_talos_entrypoint_preserves_check_mode(tmp_path, talos, entry):
    variables, _, commands = talos
    result = run_role(tmp_path, "talos", entry, variables, check=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not commands()
    assert not (tmp_path / "custom client").exists()
    assert not (tmp_path / "custom machine").exists()
    assert not (tmp_path / "client").exists()


@pytest.mark.parametrize("version", ["expected", "older", "prefix", None])
def test_upgrade_uses_installer_and_exact_server_version(tmp_path, talos, version):
    variables, defaults, commands = talos
    expected = defaults["talos_upgrade"]["installer"]["version"]
    server = {"expected": expected, "older": "v1.0.0", "prefix": expected + "0", None: ""}[version]
    node = {
        "apiVersion": "v1",
        "kind": "Node",
        "metadata": {"name": "fixture-node"},
        "spec": {"unschedulable": True},
        "status": {"addresses": [{"type": "InternalIP", "address": variables["talos_node"]}]},
    }
    with cluster_api(tmp_path, {"objects": {"/api/v1/nodes/fixture-node": node}, "events": []}) as (
        connection,
        observed,
    ):
        result = run_role(
            tmp_path,
            "talos",
            "upgrade",
            {**variables, **connection},
            env={"SERVER_VERSION": server},
        )
        state = observed()
    assert (result.returncode == 0) == (version == "expected"), result.stdout + result.stderr
    args = commands()[0]
    installer = defaults["talos_upgrade"]["installer"]
    assert args[args.index("--image") + 1] == installer["repository"] + ":" + installer["version"]
    assert state["objects"]["/api/v1/nodes/fixture-node"]["spec"]["unschedulable"] is False
    assert all(
        event["path"].endswith("/fixture-node")
        for event in state["events"]
        if event["method"] != "GET"
    )


@pytest.mark.parametrize("entry", ["apply", "bootstrap", "reset", "upgrade_k8s"])
def test_native_commands_and_failures(tmp_path, talos, entry):
    variables, _, commands = talos
    result = run_role(tmp_path, "talos", entry, variables)
    assert result.returncode == 0, result.stdout + result.stderr
    assert commands()
    if entry == "bootstrap":
        assert [
            next(
                command
                for command in ["version", "bootstrap", "health", "kubeconfig"]
                if command in args
            )
            for args in commands()
        ] == ["version", "bootstrap", "health", "kubeconfig"]
        assert stat.S_IMODE((tmp_path / "client/kubeconfig").stat().st_mode) == 0o600
    fail = {
        "apply": "apply-config",
        "bootstrap": "health",
        "reset": "reset",
        "upgrade_k8s": "upgrade-k8s",
    }[entry]
    result = run_role(tmp_path, "talos", entry, variables, env={"FAIL": fail})
    assert result.returncode != 0
