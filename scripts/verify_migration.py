#!/usr/bin/env python3
"""One-time in-memory verification of legacy inputs against cloud values."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from bws_readonly import read_project, ProviderError

ROOT = Path(__file__).resolve().parents[1]
OLD_PROJECT = '16848a5f-8d25-4560-af64-b3b5014052e7'
OLD_IDS = {'TF_VAR_cloudflare_api_token': '480d7959-9c82-4cc4-82f0-b3d7015f58b4', 'TF_VAR_cloudflare_zone_id': 'bd1b273e-cb47-4fa9-a5f9-b3d7015f66b0', 'TF_VAR_tailscale_client_id': 'c9b296b4-06e0-426c-b9f2-b3d70141d532', 'TF_VAR_tailscale_client_secret': '13c2205a-4fa2-4c7c-85e2-b3d70141e697'}


class VerificationError(Exception):
    """Safe comparison result; no expected or actual values."""


def compare(expected):
    for key, value in expected.items():
        if os.environ.get(key) != value:
            raise VerificationError('migration-round-trip-mismatch:' + key)


def legacy_talos():
    password = os.environ.get('ANSIBLE_VAULT_PASSWORD')
    if not password:
        raise VerificationError('legacy-vault-password-required-for-one-time-verification')
    with tempfile.TemporaryDirectory(prefix='home-ops-migration-') as directory:
        path = Path(directory) / 'password'
        path.touch(mode=0o600)
        path.write_text(password)
        result = subprocess.run([str(ROOT / '.venv/bin/ansible-vault'), 'view', '--vault-password-file', str(path), str(ROOT / 'ansible/roles/talos/files/secrets.vault.yml')], capture_output=True, text=True, timeout=30, check=False)
        if result.returncode:
            raise VerificationError('legacy-vault-decryption-failed')
        return result.stdout


def verify_scope(scope, expected):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/operator_secrets.py'), 'run', scope, '--', sys.executable, str(ROOT / 'scripts/verify_migration.py'), 'compare'], input=json.dumps(expected), capture_output=True, text=True, timeout=120, check=False)
    if result.returncode:
        raise VerificationError('migration-round-trip-failed:' + scope)
    print('Migration round-trip passed: ' + scope)


def main():
    try:
        if sys.argv[1:] == ['compare']:
            compare(json.load(sys.stdin))
        else:
            talos = legacy_talos()
            verify_scope('talos', {'TALOS_SECRETS_YAML': talos})
            backend = {key: os.environ.get(key, '') for key in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY')}
            if not all(backend.values()) or not os.environ.get('BWS_ACCESS_TOKEN'):
                raise VerificationError('legacy-backend-and-bitwarden-inputs-required-for-verification')
            values = read_project(['--color', 'no', '--server-url', 'https://vault.bitwarden.com', 'secret', 'list', OLD_PROJECT, '--output', 'json'])
            by_id = {item['id']: item['value'] for item in values}
            if any(identifier not in by_id for identifier in OLD_IDS.values()):
                raise VerificationError('legacy-infrastructure-item-missing')
            backend.update({key: by_id[identifier] for key, identifier in OLD_IDS.items()})
            verify_scope('terraform', backend)
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, (VerificationError, ProviderError)) else 'migration-verification-failed'
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
