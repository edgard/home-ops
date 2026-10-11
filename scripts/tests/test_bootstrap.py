from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from test_secrets import ROOT, module


class BootstrapContracts(unittest.TestCase):
    def test_shared_account_accepts_only_configured_projects(self):
        import json
        import tomllib
        from urllib.parse import urlparse
        bootstrap = module('bootstrap')
        providers = tomllib.loads((ROOT / 'secretspec.toml').read_text())['providers']
        projects = [{'id': urlparse(provider['uri']).netloc} for provider in providers.values()]
        values = [{'key': 'argocd_repo_username', 'value': 'fixture'}, {'key': 'argocd_repo_password', 'value': 'PRIVATE'}]
        with patch.object(bootstrap, 'checked', return_value=json.dumps(projects)), patch.object(bootstrap, 'read_project', return_value=values), patch.object(bootstrap, 'source_manifest_paths', return_value=[]):
            self.assertEqual(bootstrap.application_access('synthetic')['argocd_repo_username'], 'fixture')

        with patch.object(bootstrap, 'checked', return_value=json.dumps(projects + [{'id': 'unconfigured'}])), patch.object(bootstrap, 'read_project') as read:
            with self.assertRaisesRegex(bootstrap.PreflightError, '^eso-project-access-mismatch$'):
                bootstrap.application_access('synthetic')
            read.assert_not_called()

    def test_cluster_cloud_preflight_precedes_all_node_mutation(self):
        tasks = yaml.safe_load((ROOT / 'ansible/playbooks/cluster-create.yml').read_text())[0]['tasks']
        self.assertEqual(tasks[0].get('ansible.builtin.include_role', {}).get('tasks_from'), 'preflight')
        self.assertEqual(tasks[0]['ansible.builtin.include_role']['name'], 'platform')

    def test_generation_explicit_repository_versions_and_installer(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/talos/tasks/generate.yml').read_text())
        commands = [t['ansible.builtin.command']['argv'] for t in tasks[1]['block'] if 'ansible.builtin.command' in t]
        gen = next(command for command in commands if 'gen' in command)
        self.assertIn('--talos-version', gen)
        self.assertIn('--kubernetes-version', gen)
        self.assertIn('--install-image', gen)
        self.assertNotIn('lookup', str(gen))

    def test_store_wait_before_argo_handoff(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/platform/tasks/external_secrets.yml').read_text())
        self.assertTrue(any('platform_external_secrets_store_waits' in str(task) for task in tasks))
        store = yaml.safe_load((ROOT / 'apps/platform-system/external-secrets/manifests/external-secrets-store.clustersecretstore.yaml').read_text())
        self.assertEqual(set(store['spec']['conditions'][0]['namespaces']), {'argocd', 'media', 'platform-system', 'selfhosted'})

    def test_malformed_talos_secret_fails_safely(self):
        bootstrap = module('bootstrap')
        for secret in ('PRIVATE: [', '[]', 'cluster: {}', ''):
            with self.assertRaisesRegex(bootstrap.PreflightError, '^invalid-talos-material$'):
                bootstrap.validate_talos(secret)

    def test_versions_derived_from_sources(self):
        bootstrap = module('bootstrap')
        defaults = yaml.safe_load((ROOT / 'ansible/roles/talos/defaults/main.yml').read_text())
        upgrade = yaml.safe_load((ROOT / 'apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml').read_text())
        versions = bootstrap.generation_targets(ROOT)
        self.assertEqual(versions['talos'], defaults['talos_upgrade']['installer']['version'])
        self.assertEqual(versions['kubernetes'], upgrade['spec']['kubernetes']['version'])
        self.assertEqual(versions['installer'], defaults['talos_upgrade']['installer']['repository'] + ':' + versions['talos'])

    def test_custom_client_paths_explicit(self):
        for filename in ('apply.yml', 'bootstrap.yml'):
            source = (ROOT / 'ansible/roles/talos/tasks' / filename).read_text()
            self.assertIn('talos_config_path', source)
        self.assertIn('kubeconfig_path', (ROOT / 'ansible/roles/talos/tasks/bootstrap.yml').read_text())


if __name__ == '__main__':
    unittest.main()

class RepositoryAuthTests(unittest.TestCase):
    def test_invalid_github_token_rejected_without_echoing(self):
        import urllib.error
        bootstrap = module('bootstrap')
        self.assertTrue(hasattr(bootstrap, 'authenticate_repository'), 'An anonymous Git fetch cannot prove repository credentials are valid')
        error = urllib.error.HTTPError('url', 401, 'PRIVATE', {}, None)
        self.addCleanup(error.close)
        with patch.object(bootstrap.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaisesRegex(bootstrap.PreflightError, '^repository-authentication-failed$'):
                bootstrap.authenticate_repository({'argocd_repo_username': 'fixture', 'argocd_repo_password': 'PRIVATE'})

class MigrationPathTests(unittest.TestCase):
    def test_machine_config_path_accepts_nonsecret_environment_override(self):
        defaults = yaml.safe_load((ROOT / 'ansible/roles/talos/defaults/main.yml').read_text())
        self.assertIn("lookup('env', 'TALOS_CONTROLPLANE_CONFIG_PATH')", defaults['talos_controlplane_config_path'])

class RequiredInputTests(unittest.TestCase):
    def test_missing_bootstrap_values_is_rejected_before_cloud_access(self):
        bootstrap = module('bootstrap')
        self.assertTrue(hasattr(bootstrap, 'validate_required_inputs'), 'Required platform files must be checked before node mutation')
        original = type(ROOT).is_file
        def present(path):
            return False if str(path).endswith('apps/platform-system/cert-manager/values.yaml') else original(path)
        with patch.object(type(ROOT), 'is_file', present):
            with self.assertRaisesRegex(bootstrap.PreflightError, '^required-bootstrap-file-missing$'):
                bootstrap.validate_required_inputs(ROOT)
