#!/usr/bin/env python3
"""Launch operator commands through the checked-in SecretSpec contract."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'secretspec.toml'
LEGACY = {'BWS_ACCESS_TOKEN', 'BW_ACCESS_TOKEN', 'ANSIBLE_VAULT_PASSWORD', 'ANSIBLE_VAULT_PASSWORD_FILE', 'ANSIBLE_VAULT_IDENTITY_LIST', 'AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_DEFAULT_PROFILE', 'AWS_SHARED_CREDENTIALS_FILE', 'AWS_CONFIG_FILE'}


def clean_environment(source):
    declarations = tomllib.loads(MANIFEST.read_text())['profiles']['default']
    return {key: value for key, value in source.items() if key not in LEGACY and key not in declarations and not key.startswith(('SECRETSPEC_', 'TF_CLI_ARGS'))}


def tools(env):
    for tool, expected in (('secretspec', (0, 21, 1)), ('bws', (0, 3, 0))):
        path = shutil.which(tool, path=env['PATH'])
        if not path:
            raise RuntimeError(f'{tool} is missing; see the secrets setup runbook')
        result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=10, check=False)
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', result.stdout)
        version = tuple(map(int, match.groups())) if match else ()
        if result.returncode or (version != expected if tool == 'secretspec' else version < expected):
            raise RuntimeError(f'{tool} version does not satisfy the pinned tool contract')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'check', 'login'])
    parser.add_argument('scope', nargs='?', default='cluster', choices=['cluster', 'talos', 'platform', 'terraform'])
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        env = clean_environment(os.environ)
        env['PATH'] = str(Path.home() / '.local/bin') + os.pathsep + env.get('PATH', '')
        tools(env)
        config = tomllib.loads(MANIFEST.read_text())
        if '00000000-0000-0000-0000-000000000000' in config['providers']['operator']['uri']:
            raise RuntimeError('Provision home-ops-operator and set its public project UUID in secretspec.toml first')
        env['SECRETSPEC_BWS_CLI_PATH'] = str(ROOT / 'scripts/bws_readonly.py')
        if args.action == 'login':
            command = ['secretspec', 'config', 'provider', '--file', str(MANIFEST), '--reason', 'home-ops operator machine-account login', 'login', 'operator']
        else:
            command = ['secretspec', args.action, '--file', str(MANIFEST), '--profile', 'default', '--scope', args.scope, '--reason', f'home-ops {args.scope} operator command']
            if args.action == 'check':
                command += ['--no-prompt']
            if args.action == 'run':
                child = args.command[1:] if args.command[:1] == ['--'] else args.command
                if not child:
                    raise RuntimeError('A child command is required')
                command += ['--', *child]
        return subprocess.call(command, env=env, cwd=ROOT)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        # Errors here are tool/config failures, never raw provider diagnostics.
        print(f'Operator secrets setup failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
