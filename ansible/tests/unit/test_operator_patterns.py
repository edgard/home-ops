import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

from test_secrets import ROOT


class OperatorPatterns(unittest.TestCase):
    def run_play(self, tasks, variables, directory, check=False, environment=None):
        playbook = directory / 'review.yml'
        playbook.write_text(yaml.safe_dump([{'name': 'Exercise operator tasks', 'hosts': 'localhost', 'gather_facts': False, 'vars': variables, 'tasks': tasks}]))
        env = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ['PATH'])
        env.update(environment or {})
        return subprocess.run([str(ROOT / '.venv/bin/ansible-playbook'), str(playbook)] + (['--check'] if check else []), cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)

    def test_confirmed_restore_check_mode_skips_execution(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/restic/tasks/main.yml').read_text())
        execution = next(task for task in tasks if task.get('ansible.builtin.include_tasks') == 'execute.yml')
        for confirmed, check, entered in [(True, True, False), (False, False, False), (True, False, True)]:
            with self.subTest(confirmed=confirmed, check=check), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                marker = directory / 'execution'
                (directory / 'execute.yml').write_text(yaml.safe_dump([{'name': 'Record transaction entry', 'ansible.builtin.copy': {'content': 'entered', 'dest': str(marker), 'mode': '0600'}, 'check_mode': False}]))
                result = self.run_play([execution], {'restic_restore_test_mode': False, 'restic_restore_confirm': confirmed}, directory, check=check)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(marker.exists(), entered, 'Only a confirmed ordinary run may enter the transaction')

    def test_direct_restore_exec_is_skipped_in_check_mode(self):
        for source in ('execute_prepare_app.yml', 'execute_restore_app.yml'):
            task = next(task for task in yaml.safe_load((ROOT / 'ansible/roles/restic/tasks' / source).read_text()) if 'kubernetes.core.k8s_exec' in task)
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                marker = directory / 'executed'
                modules = directory / 'ansible_collections/kubernetes/core/plugins/modules'
                modules.mkdir(parents=True)
                # A disposable exec module reproduces the dependency's check-mode side effect without any API access.
                (modules / 'k8s_exec.py').write_text('from ansible.module_utils.basic import AnsibleModule\nfrom pathlib import Path\n' + f"module = AnsibleModule(argument_spec={{name: {{'type': 'str'}} for name in ['kubeconfig', 'context', 'namespace', 'pod', 'command']}}, supports_check_mode=True)\nPath({str(marker)!r}).touch()\nmodule.exit_json(changed=True, rc=0)\n")
                variables = {'kubeconfig_path': str(directory / 'unused'), 'kube_context': 'fixture', 'restic_restore_namespace': 'fixture', 'restic_restore_pod_name': 'fixture', 'restic_restore_retry_lock': '1s', 'restic_restore_effective_snapshot': 'fixture', 'restic_restore_snapshot_host': 'fixture', 'restic_restore_snapshot_tag': 'fixture', 'restic_restore_snapshot_path': '/data/appdata', 'restic_restore_target_root': '/restore', 'restic_restore_app_plan': {'restore_paths': ['/restore/data/appdata/fixture/pvc'], 'pvc_paths': ['/data/appdata/fixture/pvc']}}
                for check in (False, True):
                    result = self.run_play([task], variables, directory, check=check, environment={'ANSIBLE_COLLECTIONS_PATH': str(directory)})
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(marker.exists(), not check)
                    marker.unlink(missing_ok=True)

    def test_server_version_is_exact_and_independent_of_client(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/talos/tasks/upgrade.yml').read_text())
        version_tasks = [task for task in tasks if 'talos_upgrade_version' in json.dumps(task)]
        for server, client, accepted in [('v1.13.10', 'v1.13.11', False), ('v1.13.110', 'v1.13.11', False), (None, 'v1.13.11', False), ('v1.13.11', 'v1.14.2', True)]:
            with self.subTest(server=server, client=client), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                binary = directory / 'talosctl'
                output = f'Client:\n  Tag: {client}\nServer:\n  Tag: {server}\n'
                binary.write_text('#!/usr/bin/env python3\nimport json,sys\n' + f"print(json.dumps({{'version': {{'tag': {server!r}}}}}) if '--json' in sys.argv else {output!r})\n")
                binary.chmod(0o755)
                variables = {'talos_node': '192.0.2.10', 'talos_config_path': str(directory / 'config'), 'talos_upgrade': {'installer': {'version': 'v1.13.11'}}}
                result = self.run_play(version_tasks, variables, directory)
                self.assertEqual(result.returncode == 0, accepted, result.stdout + result.stderr)

    def test_operator_validation_tracks_configured_secretspec_pin(self):
        task = next(task for task in yaml.safe_load((ROOT / 'ansible/roles/operator_secrets/tasks/validate.yml').read_text()) if 'ansible.builtin.assert' in task and 'operator_secrets_cli_versions' in json.dumps(task))
        for actual, accepted in [('0.21.2', True), ('0.21.1', False)]:
            with self.subTest(actual=actual), tempfile.TemporaryDirectory() as temporary:
                variables = {'operator_secrets_secretspec_version': '0.21.2', 'operator_secrets_cli_versions': {'results': [{'rc': 0, 'stdout': 'secretspec ' + actual}, {'rc': 0, 'stdout': 'bws 2.1.0'}]}}
                result = self.run_play([task], variables, Path(temporary))
                self.assertEqual(result.returncode == 0, accepted, result.stdout + result.stderr)
