import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
import sys


PROJECT = '16848a5f-8d25-4560-af64-b3b5014052e7'
ARGS = ['--color', 'no', '--server-url', 'https://vault.bitwarden.com', 'secret', 'list', PROJECT, '--output', 'json']


def module(name):
    path = ROOT / 'ansible/roles/operator_secrets' / ('files/bws_readonly.py' if name == 'bws_readonly' else 'filter_plugins/secret_delivery.py')
    assert path.exists(), f'Missing implementation: {path.name}'
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.guard = module('bws_readonly')

    def test_round_trip_multiline_special_characters(self):
        value = 'line one\n$(command) `literal` \\"\n'
        data = [{'id': 'id', 'key': 'talos_secrets_yaml', 'value': value}]
        with patch.object(self.guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(data), '')):
            self.assertEqual(self.guard.read_project(ARGS), data)

    def test_duplicate_names_rejected(self):
        data = [{'id': '1', 'key': 'same', 'value': 'PRIVATE'}, {'id': '2', 'key': 'same', 'value': 'PRIVATE'}]
        with patch.object(self.guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(data), '')):
            with self.assertRaisesRegex(self.guard.ProviderError, '^duplicate-names$'):
                self.guard.read_project(ARGS)

    def test_refuse_write_and_argument_injection(self):
        for args in (['secret', 'create', 'key', 'PRIVATE'], ARGS + ['--access-token', 'PRIVATE'], ARGS[:-1]):
            with self.subTest(args=args), patch.object(self.guard.subprocess, 'run') as run:
                with self.assertRaisesRegex(self.guard.ProviderError, '^read-only-command-required$'):
                    self.guard.read_project(args)
                run.assert_not_called()

    def test_provider_error_redacted(self):
        with patch.object(self.guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'PRIVATE', 'PRIVATE')):
            with self.assertRaisesRegex(self.guard.ProviderError, '^provider-access-failed$'):
                self.guard.read_project(ARGS)

    def test_malformed_and_wrong_shape_rejected(self):
        for value in ('PRIVATE', '{}', '[{"key":"x","value":123}]', '[{"id":"x","key":"","value":"x"}]'):
            with patch.object(self.guard.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, value, '')):
                with self.assertRaisesRegex(self.guard.ProviderError, '^invalid-provider-response$'):
                    self.guard.read_project(ARGS)

    def test_timeout_and_missing_binary_safe(self):
        for error, category in ((subprocess.TimeoutExpired('bws', 30, 'PRIVATE'), 'provider-timeout'), (FileNotFoundError('PRIVATE'), 'bws-not-installed')):
            with patch.object(self.guard.subprocess, 'run', side_effect=error):
                with self.assertRaisesRegex(self.guard.ProviderError, f'^{category}$'):
                    self.guard.read_project(ARGS)


class OperatorTests(unittest.TestCase):
    def test_provider_projects_are_provisioned_and_distinct(self):
        import tomllib
        from urllib.parse import urlparse
        from uuid import UUID
        providers = tomllib.loads((ROOT / 'secretspec.toml').read_text())['providers']
        projects = [UUID(urlparse(provider['uri']).netloc) for provider in providers.values()]
        self.assertEqual(len(set(projects)), len(projects))
        self.assertTrue(all(project.int for project in projects))

    def test_manifest_has_explicit_required_read_only_scopes(self):
        import tomllib
        config = tomllib.loads((ROOT / 'secretspec.toml').read_text())
        scopes = config['scopes']
        self.assertEqual(scopes['cluster']['secrets'], ['TALOS_SECRETS_YAML', 'ESO_BWS_ACCESS_TOKEN'])
        self.assertEqual(scopes['platform']['secrets'], ['ESO_BWS_ACCESS_TOKEN'])
        for name, decl in config['profiles']['default'].items():
            self.assertTrue(decl['required'])
            self.assertEqual(len(decl['providers']), 1)
            self.assertIn('item', decl['ref'])
            self.assertNotIn('as_path', decl)
        for provider in config['providers'].values():
            self.assertEqual(provider['credentials'], {'access_token': 'keyring'})
            self.assertNotIn('cache', provider)


class PinnedIntegration(unittest.TestCase):
    def test_real_secretspec_scope_and_multiline_preservation(self):
        import shutil
        binary = shutil.which('secretspec')
        self.assertIsNotNone(binary, 'Install pinned SecretSpec for the integration check')
        version = subprocess.run([binary, '--version'], capture_output=True, text=True, check=True).stdout.strip()
        import yaml
        defaults = yaml.safe_load((ROOT / 'ansible/roles/operator_secrets/defaults/main.yml').read_text())
        self.assertEqual(version, 'secretspec ' + defaults['operator_secrets_secretspec_version'])
        value = 'line one\n$(ignored) `literal` "quotes"\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            manifest = path / 'secretspec.toml'
            manifest.write_text(f'''[project]
name = "home-ops-fixture"
revision = "1.0"
[providers]
app = {{ uri = "bws://{PROJECT}", credentials = {{ access_token = {{ provider = "env", ref = {{ item = "FIXTURE_TOKEN" }} }} }} }}
[profiles.default]
VISIBLE = {{ description = "Visible fixture", required = true, providers = ["app"], ref = {{ item = "value" }} }}
HIDDEN = {{ description = "Excluded fixture", required = true, providers = ["app"], ref = {{ item = "absent" }} }}
[scopes.test]
secrets = ["VISIBLE"]
''')
            bws = path / 'bws'
            bws.write_text('#!/usr/bin/env python3\nimport os\nprint(os.environ["FIXTURE_JSON"])\n')
            bws.chmod(0o755)
            env = dict(os.environ, FIXTURE_TOKEN='synthetic', FIXTURE_JSON=json.dumps([{'id': '1', 'key': 'value', 'value': value}]), HIDDEN='stale', PATH=str(path) + os.pathsep + os.environ['PATH'], SECRETSPEC_BWS_CLI_PATH=str(ROOT / 'ansible/roles/operator_secrets/files/bws_readonly.py'))
            child = [sys.executable, '-c', 'import json,os; print(json.dumps({"value":os.environ["VISIBLE"],"hidden":"HIDDEN" in os.environ}))']
            result = subprocess.run([binary, 'run', '--file', str(manifest), '--profile', 'default', '--scope', 'test', '--reason', 'Synthetic CI integration', '--', *child], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {'value': value, 'hidden': False})
            env['FIXTURE_JSON'] = json.dumps([{'id':'1','key':'value','value':'PRIVATE'}, {'id':'2','key':'value','value':'PRIVATE'}])
            result = subprocess.run([binary, 'run', '--file', str(manifest), '--profile', 'default', '--scope', 'test', '--reason', 'Synthetic duplicate test', '--', *child], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('PRIVATE', result.stdout + result.stderr)
            self.assertIn('duplicate-names', result.stderr)
            env['FIXTURE_JSON'] = json.dumps([{'id': '1', 'key': 'value', 'value': value}])
            env['FIXTURE_TOKEN'] = ''
            env['BWS_ACCESS_TOKEN'] = 'PRIVATE_FALLBACK'
            result = subprocess.run([binary, 'check', '--file', str(manifest), '--profile', 'default', '--scope', 'test', '--reason', 'Synthetic empty credential test', '--no-prompt'], env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('PRIVATE_FALLBACK', result.stdout + result.stderr)



if __name__ == '__main__':
    unittest.main()
