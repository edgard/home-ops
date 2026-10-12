"""Normalize tracked repository configuration for declarative policy evaluation."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib
from urllib.parse import urlparse
from uuid import UUID

import json5
import yaml


def project(uri):
    parsed = urlparse(uri)
    try:
        value = UUID(parsed.netloc)
    except ValueError:
        return ''
    return str(value) if parsed.scheme == 'bws' and value.int and not parsed.path else ''


def flatten(tasks):
    for task in tasks:
        branches = ('block', 'rescue', 'always')
        if any(branch in task for branch in branches):
            for branch in branches:
                yield from flatten(task.get(branch, []))
        else:
            yield task


def validation_inventory(tasks, render_tasks):
    # Retain the complete unevaluated document: flags can be supplied by sibling
    # facts, task variables, or enclosing blocks rather than literal argv items.
    result = {'render': [], 'export': [], 'schema': [], 'configuration': tasks, 'helm_templates': []}
    for position, task in enumerate(flatten(tasks)):
        include = task.get('ansible.builtin.include_tasks', {})
        include = include.get('file', '') if isinstance(include, dict) else include
        if include == 'render-app.yml':
            result['render'].append(position)
        command = task.get('ansible.builtin.command', {})
        command = command.get('argv', command.get('cmd', '')) if isinstance(command, dict) else command
        encoded = json.dumps(command)
        if '/files/export_schemas.py' in encoded:
            result['export'].append(position)
        if 'kubeconform' in encoded:
            result['schema'].append(position)
    for task in flatten(render_tasks):
        command = task.get('ansible.builtin.command', {})
        command = command.get('argv', command.get('cmd', '')) if isinstance(command, dict) else command
        if isinstance(command, list) and command[:2] == ['helm', 'template']:
            result['helm_templates'].append(command)
    return result


def inventory(root):
    root = Path(root)
    def read_yaml(path):
        return yaml.safe_load((root / path).read_text())
    secrets = tomllib.loads((root / 'secretspec.toml').read_text())
    for provider in secrets['providers'].values():
        provider['project'] = project(provider['uri'])
    # The native HCL parser retains expression references rather than evaluating them.
    tracked = subprocess.run(['git', 'ls-files', '-z', '--', 'terraform'], cwd=root, capture_output=True, text=True, check=True, timeout=30)
    terraform_paths = [root / path for path in tracked.stdout.split('\0') if path.endswith('.tf')]
    parsed = subprocess.run(['conftest', 'parse', *map(str, terraform_paths)], capture_output=True, text=True, check=True, timeout=30)
    terraform = {str(Path(path).relative_to(root / 'terraform')): document for path, document in json.loads(parsed.stdout).items()}
    eso = read_yaml('apps/platform-system/tailscale-router/manifests/tailscale-router-credentials.externalsecret.yaml')
    talos = read_yaml('ansible/roles/talos/defaults/main.yml')
    patch = next(yaml.safe_load_all((root / 'ansible/roles/talos/files/controlplane-patch.yaml').read_text()))
    paths = ['scripts', 'ansible/vault/operator.yml', 'ansible/roles/talos/files/secrets.vault.yml', 'ansible/playbooks/secrets-setup.yml', 'ansible/playbooks/secrets-sync-cluster-token.yml']
    return {
        'secrets': secrets,
        'tailscale_eso_item': eso['spec']['data'][0]['remoteRef']['key'],
        'terraform': terraform,
        'renovate': json5.loads((root / '.renovaterc.json5').read_text(), allow_duplicate_keys=False),
        'tasks': read_yaml('Taskfile.yaml')['tasks'],
        'paths': {path: (root / path).exists() for path in paths},
        'talos': {'installer_version': talos['talos_upgrade']['installer']['version'], 'patch_image': patch['machine']['install']['image'], 'kubernetes_version': read_yaml('apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml')['spec']['kubernetes']['version']},
        'validation': validation_inventory(read_yaml('ansible/roles/kubernetes_validation/tasks/main.yml'), read_yaml('ansible/roles/kubernetes_validation/tasks/render-app.yml')),
    }


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(inventory(sys.argv[1])))
