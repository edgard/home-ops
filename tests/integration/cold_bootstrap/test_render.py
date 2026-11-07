"""Every shipped registered consumer uses its native source chart render."""

import subprocess

from tests.support.runtime import ROOT, load_module
from tests.support.sources import read_yaml


def test_every_shipped_registered_controller_is_held_by_native_render(tmp_path):
    cold = load_module("platform/filter_plugins/cold_recovery.py")
    registry = read_yaml(ROOT / "ansible/roles/shared_data/files/registry.yaml")
    checked = []
    missing = []
    for name, entry in {**registry["consumers"], **registry["file_consumers"]}.items():
        directory = ROOT / "apps" / entry["namespace"] / name
        if not directory.exists():
            missing.append(name)
            continue
        metadata = read_yaml(directory / "app.yaml")["chart"]
        command = [
            "helm",
            "template",
            name,
            metadata["repo"],
            "--version",
            str(metadata["version"]),
            "--namespace",
            entry["namespace"],
            "--include-crds",
            "-f",
            str(directory / "values.yaml"),
        ]
        if metadata.get("name"):
            command = [
                "helm",
                "template",
                name,
                metadata["name"],
                "--repo",
                metadata["repo"],
                *command[4:],
            ]
        output = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=90
        ).stdout
        raw = cold.cold_yaml(output)
        resources = cold.cold_resources(
            raw, registry, [name], entry["namespace"], name, "c" * 32
        )
        controllers = [
            r for r in resources if r["kind"] in {"Deployment", "StatefulSet"}
        ]
        assert controllers and all(r["spec"]["replicas"] == 0 for r in controllers)
        expected = {(r["kind"], r["name"]) for r in entry["workloads"]}
        assert expected <= {(r["kind"], r["metadata"]["name"]) for r in controllers}
        for controller in controllers:
            assert controller["spec"]["template"]["spec"]["containers"]
            assert all(
                c["image"] for c in controller["spec"]["template"]["spec"]["containers"]
            )
        assert all(r["spec"]["suspend"] for r in resources if r["kind"] == "CronJob")
        checked.append(name)
    assert checked
    # Missing registry definitions are an explicit cold-bootstrap refusal boundary.
    assert set(checked) | set(missing) == set(registry["consumers"]) | set(
        registry["file_consumers"]
    )


def test_native_foundations_have_no_detached_jobs_or_early_routes(tmp_path):
    import yaml

    cold = load_module("platform/filter_plugins/cold_recovery.py")
    defaults = read_yaml(ROOT / "ansible/roles/platform/defaults/main.yml")
    for spec in defaults["platform_bootstrap_releases"]:
        metadata = read_yaml(ROOT / spec["app_metadata"])["chart"]
        values = tmp_path / (spec["name"] + ".yaml")
        values.write_text(
            yaml.safe_dump(defaults["platform_cold_helm_values"].get(spec["name"], {}))
        )
        command = [
            "helm",
            "template",
            spec["name"],
            metadata.get("name", metadata["repo"]),
            "--version",
            str(metadata["version"]),
            "--namespace",
            spec["namespace"],
            "--include-crds",
            "--no-hooks",
            "--api-versions",
            "gateway.networking.k8s.io/v1/HTTPRoute",
            "-f",
            str(ROOT / spec["values_file"]),
            "-f",
            str(values),
        ]
        if metadata.get("name"):
            command += ["--repo", metadata["repo"]]
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=90
        )
        resources = cold.cold_yaml(result.stdout)
        assert resources
        assert not {"Job", "CronJob", "Pod", "HTTPRoute", "Ingress", "DNSEndpoint"} & {
            r["kind"] for r in resources
        }
        assert not any(
            "helm.sh/hook" in r["metadata"].get("annotations", {}) for r in resources
        )
        if spec["name"] == "argocd":
            redis = next(
                r
                for r in resources
                if r["kind"] == "Deployment" and r["metadata"]["name"] == "argocd-redis"
            )
            env = redis["spec"]["template"]["spec"]["containers"][0]["env"]
            assert (
                next(e for e in env if e["name"] == "REDIS_PASSWORD")["valueFrom"][
                    "secretKeyRef"
                ]["name"]
                == "argocd-redis"
            )
