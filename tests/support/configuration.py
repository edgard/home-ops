"""Repository configuration assertions, expressed against parsed sources."""

import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from uuid import UUID

from ansible.utils.version import SemanticVersion
import hcl2
from hcl2.utils import SerializationOptions

from tests.support.sources import read_yaml, read_toml, read_json5


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
        assert (
            declaration["providers"] == ["bitwarden"]
        ), f"one provider: {name}"
        assert (
            isinstance(declaration["ref"]["item"], str) and declaration["ref"]["item"]
        ), f"item reference: {name}"
        assert "as_path" not in declaration, f"environment delivery: {name}"
    for scope, expected in {
        "cluster": {"TALOS_SECRETS_YAML", "ESO_BWS_ACCESS_TOKEN"},
        "platform": {"ESO_BWS_ACCESS_TOKEN"},
    }.items():
        actual = config["scopes"][scope]["secrets"]
        assert set(actual) == expected and len(actual) == len(expected), f"scope inputs: {scope}"
        assert expected <= declarations.keys(), f"declared scope inputs: {scope}"
    assert declarations["TF_VAR_tailscale_client_id"]["ref"]["item"] == "tailscale_oauth_client_id"
    shared = declarations["TF_VAR_tailscale_client_secret"]
    assert (
        shared["ref"]["item"] == tailscale_item
    ), "shared Tailscale application item"


def assert_targets(talos, kubernetes, patch):
    assert all(
        isinstance(value, str) and value for value in (talos, kubernetes, patch)
    ), "nonempty upgrade targets"
    assert SemanticVersion(talos.removeprefix("v")) < SemanticVersion(
        "1.14.0"
    ), "Talos installer migration required"
    assert SemanticVersion(kubernetes.removeprefix("v")) < SemanticVersion(
        "1.37.0"
    ), "upgrade deployed Talos before Kubernetes"
    assert patch.endswith(":" + talos), "Talos patch/default alignment"


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
            result[path.relative_to(root)] = hcl2.load(source, serialization_options=options)
    return result


def assert_terraform(root):
    documents = terraform_sources(root)
    assert "bitwarden-secrets" not in json.dumps(
        list(documents.values())
    ), "retired Bitwarden provider"
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
    assert SemanticVersion(pins[0]) < SemanticVersion(limits[0]), "Cloudflare compatibility limit"


def assert_repository(root):
    root = Path(root)
    eso = read_yaml(
        root
        / "apps/platform-system/tailscale-router/manifests/tailscale-router-credentials.externalsecret.yaml"
    )
    refs = [
        entry["remoteRef"]["key"]
        for entry in eso["spec"]["data"]
        if entry["secretKey"] == "client_secret"
    ]
    assert len(refs) == 1, "one Tailscale OAuth secret reference"
    store = read_yaml(root / "apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml")
    assert_secrets(read_toml(root / "secretspec.toml"), refs[0], store["spec"]["provider"]["bitwardensecretsmanager"]["projectID"])
    defaults = read_yaml(root / "ansible/roles/talos/defaults/main.yml")
    patch = read_yaml(root / "ansible/roles/talos/files/controlplane-patch.yaml", multiple=True)[0]
    upgrade = read_yaml(
        root / "apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
    )
    assert_targets(
        defaults["talos_upgrade"]["installer"]["version"],
        upgrade["spec"]["kubernetes"]["version"],
        patch["machine"]["install"]["image"],
    )
    assert_terraform(root)
    tasks = read_yaml(root / "Taskfile.yaml")["tasks"]
    assert "tf:migrate-secret-state" not in tasks, "retired migration command"
    assert "scripts/" not in json.dumps(tasks), "role-owned orchestration"
    for name in ("secrets-sync-cluster-token",):
        assert (root / f"ansible/playbooks/{name}.yml").is_file(), f"CLI entry point: {name}"
    retired = [
        "scripts",
        "ansible/vault/operator.yml",
        "ansible/roles/talos/files/secrets.vault.yml",
    ]
    assert not any((root / path).exists() for path in retired), "retired secret workflows"
    artifacts = [
        "ansible/roles/talos/files/secrets.yaml",
        ".envrc.backup",
        ".vault-password.backup",
        "ansible/roles/talos/files/secrets.yaml.backup",
        "terraform/crash.123.log",
        "terraform/terraform.tfstate.backup",
        "terraform/recovery.tfplan.backup",
    ]
    ignored = subprocess.run(
        ["git", "check-ignore", "--", *artifacts],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert ignored.returncode == 0 and set(ignored.stdout.splitlines()) == set(
        artifacts
    ), "ignored credentials and recovery artifacts"
    tracked = subprocess.run(
        ["git", "ls-files", "--", artifacts[0], *retired[1:]],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert not tracked.stdout, "tracked credential artifacts"


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)
