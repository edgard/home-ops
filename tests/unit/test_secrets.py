import json
import subprocess
from unittest.mock import patch
import pytest


@pytest.fixture
def guard(module_loader):
    return module_loader("operator_secrets/files/bws_readonly.py")


PROJECT = "12345678-1234-1234-1234-123456789abc"
ARGS = [
    "--color",
    "no",
    "--server-url",
    "https://vault.bitwarden.com",
    "secret",
    "list",
    PROJECT,
    "--output",
    "json",
]


def test_round_trip_multiline_special_characters(guard):
    value = 'line one\n$(command) `literal` \\"\n'
    data = [{"id": "id", "key": "talos_secrets_yaml", "value": value}]
    with patch.object(
        guard.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, json.dumps(data), ""),
    ):
        assert guard.read_project(ARGS) == data


def test_duplicate_names_rejected(guard):
    data = [
        {"id": "1", "key": "same", "value": "PRIVATE"},
        {"id": "2", "key": "same", "value": "PRIVATE"},
    ]
    with patch.object(
        guard.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 0, json.dumps(data), ""),
    ):
        with pytest.raises(guard.ProviderError, match="^duplicate-names$"):
            guard.read_project(ARGS)


def test_refuse_write_and_argument_injection(guard):
    for args in (
        ["secret", "create", "key", "PRIVATE"],
        ARGS + ["--access-token", "PRIVATE"],
        ARGS[:-1],
    ):
        with patch.object(guard.subprocess, "run") as run:
            with pytest.raises(guard.ProviderError, match="^read-only-command-required$"):
                guard.read_project(args)
            run.assert_not_called()


def test_provider_error_redacted(guard):
    with patch.object(
        guard.subprocess,
        "run",
        return_value=subprocess.CompletedProcess([], 1, "PRIVATE", "PRIVATE"),
    ):
        with pytest.raises(guard.ProviderError, match="^provider-access-failed$"):
            guard.read_project(ARGS)


def test_malformed_and_wrong_shape_rejected(guard):
    for value in (
        "PRIVATE",
        "{}",
        '[{"key":"x","value":123}]',
        '[{"id":"x","key":"","value":"x"}]',
    ):
        with patch.object(
            guard.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, value, "")
        ):
            with pytest.raises(guard.ProviderError, match="^invalid-provider-response$"):
                guard.read_project(ARGS)


def test_timeout_and_missing_binary_safe(guard):
    for error, category in (
        (subprocess.TimeoutExpired("bws", 30, "PRIVATE"), "provider-timeout"),
        (FileNotFoundError("PRIVATE"), "bws-not-installed"),
    ):
        with patch.object(guard.subprocess, "run", side_effect=error):
            with pytest.raises(guard.ProviderError, match=f"^{category}$"):
                guard.read_project(ARGS)
