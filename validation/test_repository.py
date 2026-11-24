"""Direct checks for credential exposure and infrastructure compatibility."""

import re
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import hcl2
from hcl2.utils import SerializationOptions
from packaging.specifiers import SpecifierSet
from packaging.version import Version as SemanticVersion

from validation.sources import read_json5, read_yaml


def read_toml(path):
    return tomllib.loads(Path(path).read_text())


def assert_secrets(config, tailscale_item, project_id):
    providers = config["providers"]
    assert set(providers) == {"bitwarden"}, "one Bitwarden provider"
    provider = providers["bitwarden"]
    uri = urlsplit(provider["uri"])
    project = UUID(uri.netloc)
    assert uri.scheme == "bws" and not uri.path and project.int, "Bitwarden project URI"
    assert project == UUID(project_id), "shared Bitwarden project for CLI and ESO"
    assert provider["credentials"] == {"access_token": "keyring"}, "Keychain credential"
    assert "cache" not in provider, "no credential cache"
    declarations = config["profiles"]["default"]
    assert declarations, "required secret declarations"
    for name, declaration in declarations.items():
        assert declaration["required"] is True, f"required secret: {name}"
        assert declaration["providers"] == ["bitwarden"], f"one provider: {name}"
        assert (
            isinstance(declaration["ref"]["item"], str) and declaration["ref"]["item"]
        ), f"item reference: {name}"
        assert "as_path" not in declaration, f"environment delivery: {name}"
    for scope, expected in {
        "talos": {"TALOS_SECRETS_YAML"},
        "cluster": {"TALOS_SECRETS_YAML", "ESO_BWS_ACCESS_TOKEN"},
        "platform": {"ESO_BWS_ACCESS_TOKEN"},
        "terraform": {
            name for name in declarations if name.startswith(("AWS_", "TF_VAR_"))
        },
    }.items():
        actual = config["scopes"][scope]["secrets"]
        assert set(actual) == expected and len(actual) == len(expected), (
            f"scope inputs: {scope}"
        )
        assert expected <= declarations.keys(), f"declared scope inputs: {scope}"
    assert (
        declarations["TF_VAR_tailscale_client_id"]["ref"]["item"]
        == "tailscale_oauth_client_id"
    )
    shared = declarations["TF_VAR_tailscale_client_secret"]
    assert shared["ref"]["item"] == tailscale_item, "shared Tailscale application item"


def terraform_sources(root):
    root = Path(root)
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "terraform"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    paths = [root / path for path in tracked.stdout.split("\0") if path.endswith(".tf")]
    assert paths, "tracked Terraform sources"
    options = SerializationOptions(
        strip_string_quotes=True, with_comments=False, explicit_blocks=False
    )
    result = {}
    for path in paths:
        with path.open() as source:
            result[path.relative_to(root)] = hcl2.load(
                source, serialization_options=options
            )
    return result


def assert_terraform(root):
    documents = terraform_sources(root)
    pins = [
        provider["version"]
        for document in documents.values()
        for block in document.get("terraform", [])
        for required in block.get("required_providers", [])
        for provider in required.values()
        if provider.get("source") == "cloudflare/cloudflare" and "version" in provider
    ]
    rules = read_json5(Path(root) / ".renovaterc.json5")["packageRules"]
    limits = [
        rule["allowedVersions"][1:]
        for rule in rules
        if "terraform-provider" in rule.get("matchDatasources", [])
        and "cloudflare/cloudflare" in rule.get("matchPackageNames", [])
        and rule.get("allowedVersions", "").startswith("<")
    ]
    assert len(pins) == len(limits) == 1, "unambiguous Cloudflare compatibility pin"
    assert SemanticVersion(pins[0]) < SemanticVersion(limits[0]), (
        "Cloudflare compatibility limit"
    )


def test_secret_scope_and_project_alignment(repo_root):
    store = read_yaml(
        repo_root
        / "apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml"
    )
    tailscale = read_yaml(
        repo_root
        / "apps/platform-system/tailscale-router/manifests/tailscale-router-credentials.externalsecret.yaml"
    )
    item = next(
        row["remoteRef"]["key"]
        for row in tailscale["spec"]["data"]
        if row["secretKey"] == "client_secret"
    )
    assert_secrets(
        read_toml(repo_root / "secretspec.toml"),
        item,
        store["spec"]["provider"]["bitwardensecretsmanager"]["projectID"],
    )


def test_private_artifacts_stay_ignored_and_untracked(repo_root):
    artifacts = [
        ".envrc.backup",
        ".vault-password.backup",
        "ansible/roles/talos/files/secrets.yaml",
        "ansible/roles/talos/files/secrets.yaml.backup",
        "terraform/crash.123.log",
        "terraform/terraform.tfstate.backup",
        "terraform/recovery.tfplan.backup",
    ]
    ignored = subprocess.run(
        ["git", "check-ignore", "--", *artifacts],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert set(ignored.stdout.splitlines()) == set(artifacts)
    patterns = [
        ".envrc*",
        ".vault-password*",
        "ansible/roles/talos/files/secrets.*",
        "terraform/**/terraform.tfstate*",
        "terraform/**/*.tfplan*",
        "terraform/**/crash*.log",
    ]
    tracked = subprocess.run(
        ["git", "ls-files", "--", *patterns],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert not tracked.stdout, "sensitive artifacts must not be tracked"


def test_talos_install_and_upgrade_images_match(repo_root):
    upgrade = read_yaml(
        repo_root / "apps/platform-system/tuppr/manifests/tuppr-talos.talosupgrade.yaml"
    )
    patches = read_yaml(
        repo_root / "ansible/roles/talos/files/controlplane-patch.yaml", multiple=True
    )
    (install,) = (
        doc for doc in patches if doc.get("kind") == "UnattendedInstallConfig"
    )
    assert (
        install["installer"]["image"].rsplit(":", 1)[1]
        == (upgrade["spec"]["talos"]["version"])
    )


def test_python_interpreter_alignment(repo_root):
    toolchain = read_yaml(repo_root / ".github/actions/setup-toolchain/action.yml")
    python = next(
        step
        for step in toolchain["runs"]["steps"]
        if step.get("uses", "").startswith("actions/setup-python@")
    )
    assert python["with"]["python-version-file"] == "pyproject.toml"
    supported = SpecifierSet(
        read_toml(repo_root / "pyproject.toml")["project"]["requires-python"]
    )
    preferred = re.search(
        r"python([0-9]+\.[0-9]+)",
        read_yaml(repo_root / "Taskfile.yaml")["vars"]["PYTHON_BIN"],
    ).group(1)
    assert preferred in supported, (
        "Task interpreter must satisfy the supported Python range"
    )


def test_cloudflare_provider_stays_below_renovate_limit(repo_root):
    assert_terraform(repo_root)
