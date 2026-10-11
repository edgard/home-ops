#!/usr/bin/env python3
"""Read-only cloud and local bootstrap preflight; never contacts the node."""
import base64
import json
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import yaml

from bws_readonly import ProviderError, read_project

ROOT = Path(__file__).resolve().parents[1]


class PreflightError(Exception):
    """Safe stage category, never raw process output or secret material."""


def validate_talos(text):
    try:
        data = yaml.safe_load(text)
        fields = {'cluster': ('id', 'secret'), 'secrets': ('bootstraptoken', 'secretboxencryptionsecret'), 'trustdinfo': ('token',), 'certs': ('etcd', 'k8s', 'k8saggregator', 'k8sserviceaccount', 'os')}
        if not isinstance(data, dict) or any(not isinstance(data.get(section), dict) or any(not data[section].get(field) for field in keys) for section, keys in fields.items()):
            raise ValueError
        return data
    except (ValueError, TypeError, yaml.YAMLError):
        raise PreflightError('invalid-talos-material') from None


def generation_targets(root):
    try:
        defaults = yaml.safe_load((root / 'ansible/roles/talos/defaults/main.yml').read_text())
        patch = next(yaml.safe_load_all((root / 'ansible/roles/talos/files/controlplane-patch.yaml').read_text()))
        upgrade = yaml.safe_load((root / 'apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml').read_text())
        installer = defaults['talos_upgrade']['installer']
        image = installer['repository'] + ':' + installer['version']
        if patch['machine']['install']['image'] != image:
            raise ValueError
        return {'talos': installer['version'], 'installer': image, 'kubernetes': upgrade['spec']['kubernetes']['version']}
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError):
        raise PreflightError('repository-generation-targets-invalid') from None


def validate_required_inputs(root):
    defaults_path = root / 'ansible/roles/platform/defaults/main.yml'
    try:
        defaults = yaml.safe_load(defaults_path.read_text())
        files = [root / 'ansible/roles/talos/files/controlplane-patch.yaml']
        for release in defaults['platform_bootstrap_releases']:
            files.extend(root / release[key] for key in ('app_metadata', 'values_file'))
            if release.get('manifests_dir') and not (root / release['manifests_dir']).is_dir():
                raise PreflightError('required-bootstrap-directory-missing')
        files += [root / defaults[key] for key in ('platform_k8tz_app_metadata', 'platform_external_secrets_store_manifest', 'platform_argocd_repo_credentials_manifest', 'platform_argocd_root_application_manifest')]
        files += [root / path for path in defaults['platform_external_secrets_bootstrap_manifests']]
        collection = root / '.ansible/collections/ansible_collections/kubernetes/core/plugins/modules'
        files += [collection / name for name in ('k8s.py', 'k8s_info.py', 'helm.py')]
        if any(not path.is_file() for path in files):
            raise PreflightError('required-bootstrap-file-missing')
        for path in files:
            if path.suffix in ('.yaml', '.yml'):
                list(yaml.safe_load_all(path.read_text()))
        if not importlib.util.find_spec('kubernetes'):
            raise PreflightError('bootstrap-python-dependency-missing')
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        raise PreflightError('required-bootstrap-input-invalid') from None


def source_manifest_paths():
    # Ignored/untracked editor copies must never become bootstrap inputs.
    paths = checked(['git', 'ls-files', '-z', '--', 'apps'], 'tracked-manifest-inventory-failed').split('\0')
    return [ROOT / name for name in paths if Path(name).match('apps/*/*/manifests/*.yaml')]


def checked(argv, category, env=None):
    try:
        result = subprocess.run(argv, env=env, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode:
            raise PreflightError(category)
        return result.stdout
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise PreflightError(category) from None


def application_access(token):
    store = yaml.safe_load((ROOT / 'apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml').read_text())
    project = store['spec']['provider']['bitwardensecretsmanager']['projectID']
    env = dict(os.environ, BWS_ACCESS_TOKEN=token)
    env.pop('BW_ACCESS_TOKEN', None)
    # Validate machine account access, not merely its ability to read one project.
    projects_text = checked(['bws', '--color', 'no', '--server-url', 'https://vault.bitwarden.com', 'project', 'list', '--output', 'json'], 'eso-project-access-failed', env)
    try:
        projects = json.loads(projects_text)
        if not isinstance(projects, list) or {item['id'] for item in projects} != {project}:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise PreflightError('eso-must-access-only-application-project') from None
    try:
        with_token = os.environ.get('BWS_ACCESS_TOKEN')
        os.environ['BWS_ACCESS_TOKEN'] = token
        data = read_project(['--color', 'no', '--server-url', 'https://vault.bitwarden.com', 'secret', 'list', project, '--output', 'json'])
    except ProviderError as error:
        raise PreflightError(f'eso-{error}') from None
    finally:
        if with_token is None:
            os.environ.pop('BWS_ACCESS_TOKEN', None)
        else:
            os.environ['BWS_ACCESS_TOKEN'] = with_token
    values = {item['key']: item['value'] for item in data}
    for manifest in source_manifest_paths():
        for document in yaml.safe_load_all(manifest.read_text()):
            if isinstance(document, dict) and document.get('kind') == 'ExternalSecret':
                if any(entry['remoteRef']['key'] not in values for entry in document['spec']['data']):
                    raise PreflightError('application-secret-missing')
    if any(not values.get(key) for key in ('argocd_repo_username', 'argocd_repo_password')):
        raise PreflightError('repository-credential-missing')
    return values


def authenticate_repository(values):
    # Public ls-remote can succeed anonymously with an invalid password.
    authorization = base64.b64encode((values['argocd_repo_username'] + ':' + values['argocd_repo_password']).encode()).decode()
    request = urllib.request.Request('https://api.github.com/user', headers={'Authorization': 'Basic ' + authorization, 'Accept': 'application/vnd.github+json', 'User-Agent': 'home-ops-bootstrap'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            user = json.load(response)
        if not isinstance(user.get('login'), str) or not user['login']:
            raise ValueError
    except Exception:
        raise PreflightError('repository-authentication-failed') from None


def repository_revision(values):
    authenticate_repository(values)
    root = yaml.safe_load((ROOT / 'argocd/root.app.yaml').read_text())
    url = root['spec']['sources'][0]['repoURL']
    head = checked(['git', 'rev-parse', 'HEAD'], 'git-head-unavailable').strip()
    if checked(['git', 'status', '--porcelain', '--untracked-files=no'], 'git-status-failed').strip():
        raise PreflightError('bootstrap-requires-clean-merged-checkout')
    with tempfile.TemporaryDirectory(prefix='home-ops-git-') as directory:
        askpass = Path(directory) / 'askpass'
        askpass.write_text('#!/usr/bin/env python3\nimport os,sys\nprint(os.environ["HOME_OPS_GIT_USERNAME"] if "username" in sys.argv[1].lower() else os.environ["HOME_OPS_GIT_PASSWORD"])\n')
        askpass.chmod(0o700)
        env = dict(os.environ, HOME_OPS_GIT_USERNAME=values['argocd_repo_username'], HOME_OPS_GIT_PASSWORD=values['argocd_repo_password'], GIT_TERMINAL_PROMPT='0', GIT_ASKPASS=str(askpass))
        env.pop('GIT_CONFIG_COUNT', None)
        output = checked(['git', '-c', 'credential.helper=', '-c', 'http.extraHeader=', 'ls-remote', '--exit-code', url, 'refs/heads/master'], 'repository-authentication-failed', env)
    if output.split()[0] != head:
        raise PreflightError('bootstrap-checkout-does-not-match-remote-master')
    return head


def preflight(stage):
    for tool in ('git', 'helm', 'bws', 'talosctl'):
        if not shutil.which(tool):
            raise PreflightError(f'missing-{tool}')
    generation_targets(ROOT)
    validate_required_inputs(ROOT)
    if stage == 'cluster':
        if any(not os.environ.get(key) for key in ('TALOS_NODE', 'TALOS_CLUSTER_NAME', 'TALOS_INSTALL_DISK')):
            raise PreflightError('missing-node-cluster-or-disk-input')
        validate_talos(os.environ.get('TALOS_SECRETS_YAML', ''))
    token = os.environ.get('ESO_BWS_ACCESS_TOKEN', '')
    if not token:
        raise PreflightError('missing-scoped-eso-token')
    return repository_revision(application_access(token))


def main():
    try:
        if sys.argv[1:] == ['targets']:
            validate_talos(os.environ.get('TALOS_SECRETS_YAML', ''))
            print(json.dumps(generation_targets(ROOT)))
        elif sys.argv[1:] in (['cluster'], ['platform']):
            print(preflight(sys.argv[1]))
        else:
            raise PreflightError('invalid-preflight-stage')
        return 0
    except PreflightError as error:
        print(str(error))
        return 1
    except Exception:
        print('preflight-internal-failure')
        return 1


if __name__ == '__main__':
    sys.exit(main())
