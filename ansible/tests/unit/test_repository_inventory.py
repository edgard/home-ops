import importlib.util
from pathlib import Path
import unittest
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]


class RepositoryInventoryTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('repository_inventory', ROOT / 'ansible/roles/repository_validation/files/inventory.py')
        self.adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.adapter)

    def test_task_discovery_does_not_depend_on_display_names(self):
        tasks = [{'name': 'Any name', 'block': [
            {'ansible.builtin.include_tasks': 'render-app.yml'},
            {'ansible.builtin.command': {'argv': "{{ [ansible_playbook_python, role_path ~ '/files/export_schemas.py'] }}"}},
            {'ansible.builtin.command': {'argv': ['kubeconform', '-strict']}},
        ]}]
        result = self.adapter.validation_inventory(tasks, [{'ansible.builtin.command': {'argv': ['helm', 'template', 'fixture', '--include-crds']}}])
        self.assertEqual(result['render'], [0])
        self.assertEqual(result['export'], [1])
        self.assertEqual(result['schema'], [2])
        self.assertEqual(result['helm_templates'], [['helm', 'template', 'fixture', '--include-crds']])

    def test_non_bws_uri_cannot_be_normalized_as_a_valid_project(self):
        self.assertEqual(self.adapter.project('file://12345678-1234-1234-1234-123456789abc'), '')
        self.assertEqual(self.adapter.project('bws://00000000-0000-0000-0000-000000000000'), '')
        self.assertEqual(self.adapter.project('bws://not-a-uuid'), '')

    def test_project_normalization_uses_synthetic_uuids(self):
        self.assertEqual(self.adapter.project('bws://12345678-1234-1234-1234-123456789abc'), '12345678-1234-1234-1234-123456789abc')

    def test_disposable_root_reads_tracked_hcl_and_normalizes_repository_sources(self):
        paths = [
            'secretspec.toml', '.renovaterc.json5', 'Taskfile.yaml',
            'apps/platform-system/tailscale-router/manifests/tailscale-router-credentials.externalsecret.yaml',
            'apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml',
            'ansible/roles/talos/defaults/main.yml', 'ansible/roles/talos/files/controlplane-patch.yaml',
            'ansible/roles/kubernetes_validation/tasks/main.yml', 'ansible/roles/kubernetes_validation/tasks/render-app.yml',
        ]
        terraform = subprocess.run(['git', 'ls-files', '--', 'terraform'], cwd=ROOT, text=True, capture_output=True, check=True).stdout.splitlines()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in paths + [path for path in terraform if path.endswith('.tf')]:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, target)
            (root / 'terraform/main.tf').write_text('provider "fixture" { token = var.fixture_token }\n')
            (root / 'secretspec.toml').write_text('[providers]\nfixture = { uri = "bws://12345678-1234-1234-1234-123456789abc" }\n')
            (root / '.renovaterc.json5').write_text('{ /* block */ packageRules: [ // inline\n {allowedVersions: "<9.0.0",},],}')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            subprocess.run(['git', 'add', 'terraform'], cwd=root, check=True)
            generated = root / 'terraform/.terraform/cache.tf'
            generated.parent.mkdir()
            generated.write_text('invalid generated HCL must not be parsed')
            (root / 'terraform/private.tf').write_text('invalid untracked HCL must not be parsed')
            result = self.adapter.inventory(root)
            self.assertEqual(result['terraform']['main.tf']['provider']['fixture'][0]['token'], '${var.fixture_token}')
            self.assertEqual(result['secrets']['providers']['fixture']['project'], '12345678-1234-1234-1234-123456789abc')
            self.assertEqual(result['renovate']['packageRules'], [{'allowedVersions': '<9.0.0'}])
            self.assertNotIn('.terraform/cache.tf', result['terraform'])
            self.assertNotIn('private.tf', result['terraform'])
            (root / '.renovaterc.json5').write_text('{packageRules: [], packageRules: []}')
            with self.assertRaises(ValueError):
                self.adapter.inventory(root)

    def test_schema_flags_from_task_block_or_sibling_fact_reach_policy(self):
        import json
        import yaml
        original = yaml.safe_load((ROOT / 'ansible/roles/kubernetes_validation/tasks/main.yml').read_text())
        render = yaml.safe_load((ROOT / 'ansible/roles/kubernetes_validation/tasks/render-app.yml').read_text())
        for scope in ('task', 'block', 'set_fact'):
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as directory:
                tasks = json.loads(json.dumps(original))
                if scope == 'block':
                    block = next(task for task in tasks if 'block' in task)
                    block['vars'] = {'schema_extra_flags': ['-ignore-missing-schemas']}
                if scope == 'set_fact':
                    block = next(task for task in tasks if 'block' in task)
                    block['block'].insert(0, {'ansible.builtin.set_fact': {'schema_extra_flags': ['-ignore-missing-schemas']}})
                for task in self.adapter.flatten(tasks):
                    command = task.get('ansible.builtin.command', {})
                    if 'kubeconform' in json.dumps(command):
                        command['argv'] = command['argv'].replace('}}', '+ schema_extra_flags }}')
                        if scope == 'task':
                            task['vars'] = {'schema_extra_flags': ['-ignore-missing-schemas']}
                path = Path(directory) / 'inventory.json'
                path.write_text(json.dumps({'validation': self.adapter.validation_inventory(tasks, render)}))
                result = subprocess.run(['conftest', 'test', '--no-color', '--output', 'json', '--policy', str(ROOT / 'policy/repository'), str(path)], text=True, capture_output=True, check=False)
                messages = [failure['msg'] for entry in json.loads(result.stdout) for failure in entry['failures']]
                self.assertIn('Missing schemas must fail validation', messages)
