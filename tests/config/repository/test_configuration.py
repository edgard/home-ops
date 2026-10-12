import copy

import pytest

from tests.support.configuration import assert_secrets, assert_targets, assert_repository
from tests.support.sources import read_toml


def test_repository_configuration(repo_root):
    assert_repository(repo_root)


@pytest.mark.parametrize(
    "path,value",
    [
        (("providers", "operator", "uri"), "file://12345678-1234-1234-1234-123456789abc"),
        (("providers", "operator", "uri"), "bws://00000000-0000-0000-0000-000000000000"),
        (("providers", "operator", "credentials"), {"access_token": "env"}),
        (("providers", "operator", "cache"), True),
        (("profiles", "default", "TALOS_SECRETS_YAML", "required"), False),
        (("profiles", "default", "TALOS_SECRETS_YAML", "as_path"), True),
        (("profiles", "default", "TALOS_SECRETS_YAML", "providers"), ["operator", "applications"]),
        (("profiles", "default", "TF_VAR_cloudflare_zone_id", "providers"), ["applications"]),
        (("profiles", "default", "TF_VAR_tailscale_client_id", "ref"), {"item": "wrong"}),
        (("profiles", "default", "TF_VAR_tailscale_client_secret", "ref"), {"item": "wrong"}),
        (("scopes", "platform", "secrets"), ["TALOS_SECRETS_YAML"]),
        (("scopes", "cluster", "secrets"), ["ESO_BWS_ACCESS_TOKEN"]),
    ],
)
def test_unsafe_secret_configuration_is_rejected(repo_root, path, value):
    config = copy.deepcopy(read_toml(repo_root / "secretspec.toml"))
    current = config
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    with pytest.raises((AssertionError, ValueError)):
        assert_secrets(config, "tailscale_oauth_client_secret")


def test_scope_order_and_additional_distinct_provider_are_allowed(repo_root):
    config = read_toml(repo_root / "secretspec.toml")
    config["scopes"]["cluster"]["secrets"].reverse()
    config["providers"]["additional"] = {
        "uri": "bws://12345678-1234-1234-1234-123456789abc",
        "credentials": {"access_token": "keyring"},
    }
    assert_secrets(config, "tailscale_oauth_client_secret")
    config["providers"]["additional"]["uri"] = config["providers"]["operator"]["uri"]
    with pytest.raises(AssertionError):
        assert_secrets(config, "tailscale_oauth_client_secret")


@pytest.mark.parametrize(
    "talos,kubernetes,patch",
    [
        ("v1.14.0", "v1.36.0", "v1.14.0"),
        ("v1.13.1", "v1.37.0", "v1.13.1"),
        ("v1.13.1", "v1.36.0", "v1.13.2"),
        ("invalid", "v1.36.0", "invalid"),
        ("v1.13", "v1.36.0", "v1.13"),
        ("v1.13.1", "", "v1.13.1"),
    ],
)
def test_incompatible_or_misaligned_targets_are_rejected(talos, kubernetes, patch):
    with pytest.raises((AssertionError, ValueError)):
        assert_targets(talos, kubernetes, "factory.talos.dev/metal-installer/example:" + patch)
