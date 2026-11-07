"""Positive fresh-state exceptions use native inventory, never API failure alone."""

import json

import pytest

from tests.integration.test_data_maintenance import maintenance_api, obj
from tests.support.runtime import executable, run_role


@pytest.fixture
def fresh(tmp_path):
    node = "192.0.2.10"

    def resource(spec, name="fixture"):
        return {"node": node, "metadata": {"id": name}, "spec": spec}

    data = {
        "machinestatus": [resource({"stage": "maintenance"})],
        "discoveredvolumes": [
            resource(
                {"dev_path": "/dev/fixture", "type": "disk", "size": 1000000}, "fixture"
            )
        ],
        "mountstatus": [
            resource(
                {
                    "target": "/var",
                    "source": "/dev/fixturep6",
                    "spec": {"volumeID": "EPHEMERAL"},
                }
            )
        ],
        "etcdmember": [],
    }
    header = "NODE MODE UID GID SIZE(B) LASTMOD LABEL NAME\n"
    data["/var"] = (
        header
        + f"{node} drwxr-xr-x 0 0 100 Nov 7 12:00 .\n{node} drwxr-xr-x 0 0 100 Nov 7 12:00 lib\n"
    )
    data["/var/lib"] = (
        header
        + f"{node} drwxr-xr-x 0 0 100 Nov 7 12:00 .\n{node} drwxr-xr-x 0 0 100 Nov 7 12:00 etcd\n"
    )
    data["/var/lib/etcd"] = ".\n"
    path = tmp_path / "native-data.json"
    path.write_text(json.dumps(data))
    executable(
        tmp_path,
        "talosctl",
        """import json,os,pathlib,sys,yaml
base=pathlib.Path(__file__).parent
args=sys.argv[1:]
data=json.loads((base/'native-data.json').read_text())
with (base/'calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\\n')
if 'get' in args:
 name=args[args.index('get')+1]
 if name==os.environ.get('FAIL_PROBE'):sys.exit(93)
 print(yaml.safe_dump_all(data[name]))
elif 'ls' in args:print(data[args[args.index('ls')+1]])
elif 'apply-config' in args or 'bootstrap' in args:(base/'native-started').touch()
elif 'kubeconfig' in args:pathlib.Path(args[args.index('kubeconfig')+1]).write_text('synthetic')
elif 'version' in args:print('synthetic-version')
elif 'health' in args or 'config' in args:pass
else:raise AssertionError(args)
""",
    )
    variables = {
        "node_operation_fresh": True,
        "talos_node": node,
        "talos_install_disk": "/dev/fixture",
        "talos_cluster_name": "fixture",
        "talos_config_path": str(tmp_path / "client"),
        "talos_controlplane_config_path": str(tmp_path / "controlplane"),
        "kubeconfig_path": str(tmp_path / "absent-config"),
        "kube_context": "fixture",
        "talos_api_wait_retries": 1,
        "talos_api_wait_delay": 0,
    }
    return variables, data, path


@pytest.mark.parametrize("entry", ["apply", "bootstrap"])
def test_positive_fresh_native_inventory_allows_creation_without_api(
    tmp_path, fresh, entry
):
    variables, _, _ = fresh
    result = run_role(tmp_path, "talos", entry, variables)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "native-started").exists()


@pytest.mark.parametrize(
    "case", ["optout", "partition", "state", "wrong-node", "probe-error", "stage"]
)
def test_fresh_disk_refuses_ambiguous_or_existing_storage(tmp_path, fresh, case):
    variables, data, path = fresh
    if case == "optout":
        variables["node_operation_fresh"] = False
    if case == "partition":
        data["discoveredvolumes"][0]["spec"]["name"] = "gpt"
    if case == "state":
        data["discoveredvolumes"].append(
            {
                "node": variables["talos_node"],
                "metadata": {"id": "other"},
                "spec": {"partition_label": "EPHEMERAL"},
            }
        )
    if case == "wrong-node":
        data["discoveredvolumes"][0]["node"] = "192.0.2.99"
    if case == "stage":
        data["machinestatus"][0]["spec"]["stage"] = "running"
    path.write_text(json.dumps(data))
    result = run_role(
        tmp_path,
        "talos",
        "apply",
        variables,
        env={"FAIL_PROBE": "discoveredvolumes" if case == "probe-error" else ""},
    )
    assert result.returncode != 0
    assert not (tmp_path / "native-started").exists()


@pytest.mark.parametrize(
    "case", ["member", "probe-error", "nonempty", "unmounted", "nested", "symlink"]
)
def test_fresh_bootstrap_refuses_existing_or_unproven_etcd(tmp_path, fresh, case):
    variables, data, path = fresh
    if case == "member":
        data["etcdmember"] = [
            {
                "node": variables["talos_node"],
                "metadata": {"id": "local"},
                "spec": {"memberID": "existing"},
            }
        ]
    if case == "nonempty":
        data["/var/lib/etcd"] = ".\nmember\n"
    if case == "unmounted":
        data["mountstatus"][0]["spec"]["detached"] = True
    if case == "nested":
        data["mountstatus"].append(
            {
                "node": variables["talos_node"],
                "metadata": {"id": "nested"},
                "spec": {"target": "/var/lib/etcd", "source": "/dev/other"},
            }
        )
    if case == "symlink":
        data["/var/lib"] = data["/var/lib"].replace(
            "drwxr-xr-x 0 0 100 Nov 7 12:00 etcd",
            "Lrwxrwxrwx 0 0 100 Nov 7 12:00 etcd -> /other",
        )
    path.write_text(json.dumps(data))
    result = run_role(
        tmp_path,
        "talos",
        "bootstrap",
        variables,
        env={"FAIL_PROBE": "etcdmember" if case == "probe-error" else ""},
    )
    assert result.returncode != 0
    assert not (tmp_path / "native-started").exists()


def test_reachable_active_cold_journal_refuses_even_explicit_fresh(tmp_path, fresh):
    variables, _, _ = fresh
    cold = obj("ConfigMap", "shared-data-cold-recovery", "selfhosted")
    cold["data"] = {"journal.json": json.dumps({"phase": "bootstrapping"})}
    with maintenance_api(tmp_path, [cold]) as (connection, state):
        result = run_role(tmp_path, "talos", "apply", {**variables, **connection})
        assert result.returncode != 0
        assert not (tmp_path / "calls.jsonl").exists()
        assert not any(
            row["method"] not in {"GET", "IDENTITY"} for row in state["events"]
        )
