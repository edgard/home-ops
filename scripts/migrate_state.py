#!/usr/bin/env python3
"""Back up state and retire only the four former Bitwarden data reads."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RETIRED = {'cloudflare_token', 'cloudflare_zone_id', 'tailscale_client_id', 'tailscale_client_secret'}


class MigrationError(Exception):
    """Safe migration failure category."""


def retired_addresses(state):
    result = []
    for resource in state.get('resources', []):
        if resource.get('type') != 'bitwarden-secrets_secret':
            continue
        if resource.get('mode') != 'data' or resource.get('name') not in RETIRED or resource.get('module'):
            raise MigrationError('unexpected-bitwarden-state-address')
        result.append('data.bitwarden-secrets_secret.' + resource['name'])
    return sorted(result)


def checked(args):
    try:
        result = subprocess.run(['tofu', *args], cwd=ROOT / 'terraform', capture_output=True, text=True, timeout=600, check=False)
    except Exception:
        raise MigrationError('state-command-failed') from None
    if result.returncode:
        raise MigrationError('state-command-failed')
    return result.stdout


def preflight_plan():
    with tempfile.TemporaryDirectory(prefix='home-ops-state-plan-') as directory:
        plan = Path(directory) / 'migration.tfplan'
        plan.touch(mode=0o600)
        checked(['plan', '-input=false', '-lock-timeout=60s', '-out=' + str(plan)])
        result = json.loads(checked(['show', '-json', str(plan)]))
        for resource in result.get('resource_changes', []):
            if resource.get('mode') == 'managed' and resource['change']['actions'] != ['no-op']:
                raise MigrationError('managed-resource-changes-block-state-migration')


def main():
    try:
        checked(['init', '-input=false'])
        original = checked(['state', 'pull'])
        state = json.loads(original)
        addresses = retired_addresses(state)
        backup_dir = Path.home() / '.local/state/home-ops/state-recovery'
        backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_dir.chmod(0o700)
        backup = backup_dir / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.tfstate')
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            output.write(original)
            output.flush()
            os.fsync(output.fileno())
        if json.loads(backup.read_text()) != state:
            raise MigrationError('state-backup-verification-failed')
        print(f'Protected, verified recovery state: {backup}')
        # Data retirement may appear in this plan; managed changes must not.
        preflight_plan()
        if addresses:
            checked(['state', 'rm', '-lock-timeout=60s', *addresses])
        remaining = json.loads(checked(['state', 'pull']))
        managed_before = [r for r in state.get('resources', []) if r.get('mode') == 'managed']
        managed_after = [r for r in remaining.get('resources', []) if r.get('mode') == 'managed']
        if managed_before != managed_after or retired_addresses(remaining):
            raise MigrationError('state-migration-verification-failed-retain-backup')
        # A zero exit code proves no changes, including managed resources.
        checked(['plan', '-input=false', '-detailed-exitcode', '-lock-timeout=60s'])
        print('Retired Bitwarden data entries; no infrastructure changes planned')
        return 0
    except (MigrationError, ValueError) as error:
        print(str(error) if isinstance(error, MigrationError) else 'invalid-state-response', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
