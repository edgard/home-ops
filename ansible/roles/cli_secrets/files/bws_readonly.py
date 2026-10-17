#!/usr/bin/env python3
"""Read-only boundary around the official BWS CLI for SecretSpec."""

import json
import shutil
import subprocess
import sys
from uuid import UUID


class ProviderError(Exception):
    """Safe failure category; never includes provider output."""


def read_project(args):
    # SecretSpec 0.21.1's native provider emits this exact command shape.
    if (
        len(args) != 9
        or args[:6]
        != [
            "--color",
            "no",
            "--server-url",
            "https://vault.bitwarden.com",
            "secret",
            "list",
        ]
        or args[7:] != ["--output", "json"]
    ):
        raise ProviderError("read-only-command-required")
    try:
        UUID(args[6])
    except ValueError:
        raise ProviderError("read-only-command-required") from None
    binary = shutil.which("bws") or "bws"
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=30, check=False
        )
    except subprocess.TimeoutExpired:
        raise ProviderError("provider-timeout") from None
    except FileNotFoundError:
        raise ProviderError("bws-not-installed") from None
    except (OSError, UnicodeError):
        raise ProviderError("provider-execution-failed") from None
    if result.returncode:
        raise ProviderError("provider-access-failed")
    try:
        data = json.loads(result.stdout)
        if not isinstance(data, list) or any(
            not isinstance(item, dict)
            or not all(isinstance(item.get(key), str) for key in ("id", "key", "value"))
            or not item["key"]
            for item in data
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ProviderError("invalid-provider-response") from None
    keys = [item["key"] for item in data]
    if len(keys) != len(set(keys)):
        raise ProviderError("duplicate-names")
    return data


def main():
    try:
        data = read_project(sys.argv[1:])
    except ProviderError as error:
        print(f"Bitwarden read failed: {error}", file=sys.stderr)
        return 1
    json.dump(data, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
