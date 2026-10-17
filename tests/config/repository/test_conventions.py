import json
import re
import subprocess
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

from tests.support.configuration import terraform_sources, walk
from tests.support.runtime import ROOT
from tests.support.sources import read_json5, read_yaml


def test_ci_python_matches_supported_cli_runtime():
    toolchain = read_yaml(ROOT / ".github/actions/setup-toolchain/action.yml")
    python_steps = [
        step
        for step in toolchain["runs"]["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    ]
    assert len(python_steps) == 1
    version = python_steps[0]["with"]["python-version"]
    default = read_yaml(ROOT / "Taskfile.yaml")["vars"]["PYTHON_BIN"]
    assert f'"python{version}"' in default, "CI must install Task's default interpreter"
    rules = [
        rule
        for rule in read_json5(ROOT / ".renovaterc.json5")["packageRules"]
        if "github-actions" in rule.get("matchManagers", [])
        and "python" in rule.get("matchDepNames", [])
        and "allowedVersions" in rule
    ]
    assert rules, "Renovate must preserve Ansible's supported Python range"
    # Ansible core 2.21 supports control-node Python through 3.14.
    for rule in rules:
        supported = SpecifierSet(rule["allowedVersions"])
        assert version in supported, (
            "CI Python must stay within Ansible's supported range"
        )
        assert "3.14" in supported
        assert "3.15" not in supported


def test_native_kubernetes_module_convention():
    paths = list((ROOT / "ansible").rglob("*.yml"))
    assert paths
    for path in paths:
        for mapping in walk(read_yaml(path)):
            for module in ["ansible.builtin.command", "ansible.builtin.shell"]:
                if module in mapping:
                    assert not re.search(r"\bkubectl\b", json.dumps(mapping[module])), (
                        f"Use kubernetes.core modules: {path}"
                    )


def test_tracked_hcl_boundary_and_duplicate_json5(tmp_path):
    path = tmp_path / "terraform/main.tf"
    path.parent.mkdir()
    path.write_text('provider "fixture" { token = var.fixture_token }\n')
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "terraform"], cwd=tmp_path, check=True)
    (path.parent / "private.tf").write_text("invalid untracked input")
    generated = path.parent / ".terraform/cache.tf"
    generated.parent.mkdir()
    generated.write_text("invalid generated input")
    found = terraform_sources(tmp_path)
    assert list(found) == [Path("terraform/main.tf")]
    assert (
        found[Path("terraform/main.tf")]["provider"][0]["fixture"]["token"]
        == "${var.fixture_token}"
    )
    config = tmp_path / "renovate.json5"
    config.write_text(
        '{ /* comment */ packageRules: [ {allowedVersions: "<9.0.0",}, ],}'
    )
    assert read_json5(config) == {"packageRules": [{"allowedVersions": "<9.0.0"}]}
    config.write_text("{packageRules: [], packageRules: []}")
    with pytest.raises(ValueError):
        read_json5(config)
    path.write_text("malformed tracked input")
    with pytest.raises(Exception):
        terraform_sources(tmp_path)


def test_cli_task_entrypoints():
    tasks = read_yaml(ROOT / "Taskfile.yaml")["tasks"]
    for name, entry in [
        ("secrets:sync-cluster-token", "secrets-sync-cluster-token.yml"),
    ]:
        assert entry in json.dumps(tasks[name]), (
            f"{name} must invoke its real role entry point"
        )


@pytest.mark.parametrize("mutation", ["limit", "retired", "missing"])
def test_terraform_compatibility_and_retired_provider(tmp_path, mutation):
    import shutil

    from tests.support.configuration import assert_terraform

    for path in ROOT.glob("terraform/**/*.tf"):
        if ".terraform" in path.parts:
            continue
        target = tmp_path / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    shutil.copyfile(ROOT / ".renovaterc.json5", tmp_path / ".renovaterc.json5")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "terraform"], cwd=tmp_path, check=True)
    assert_terraform(tmp_path)
    main = tmp_path / "terraform/main.tf"
    if mutation == "limit":
        import hcl2

        with main.open() as file:
            document = hcl2.load(file)
        for block in document["terraform"]:
            for required in block.get("required_providers", []):
                for provider in required.values():
                    if (
                        isinstance(provider, dict)
                        and provider.get("source") == '"cloudflare/cloudflare"'
                    ):
                        provider["version"] = '"99.0.0"'
        main.write_text(hcl2.dumps(document))
    if mutation == "retired":
        main.write_text(main.read_text() + '\nprovider "bitwarden-secrets" {}\n')
    if mutation == "missing":
        subprocess.run(
            ["git", "rm", "-r", "-f", "terraform"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
    with pytest.raises(AssertionError):
        assert_terraform(tmp_path)
