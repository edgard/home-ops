import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml
from test_secrets import ROOT


class RoleContractLayoutTests(unittest.TestCase):
    def run_contracts(self, mutate):
        with tempfile.TemporaryDirectory() as directory:
            roles = Path(directory) / 'roles'
            shutil.copytree(ROOT / 'ansible/roles', roles)
            mutate(roles)
            env = os.environ | {'ANSIBLE_ROLES_PATH': str(ROOT / 'ansible/roles')}
            return subprocess.run(
                [str(ROOT / '.venv/bin/ansible-playbook'), str(ROOT / 'ansible/tests/role-contracts.yml'),
                 '-e', f'role_contract_role_root={roles}'],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=90,
            )

    @staticmethod
    def edit(roles, source, mutate):
        path = roles / source
        tasks = yaml.safe_load(path.read_text())
        mutate(tasks)
        path.write_text(yaml.safe_dump(tasks, sort_keys=False))

    def test_renamed_operations_and_harmless_added_tasks_are_allowed(self):
        def add_tasks(tasks):
            for task in list(tasks):
                task['name'] = 'Renamed operation'
                for branch in ('block', 'rescue', 'always'):
                    if branch in task:
                        add_tasks(task[branch])
            tasks.insert(0, {'name': 'Harmless diagnostic', 'ansible.builtin.debug': {'msg': 'fixture'}})

        def mutate(roles):
            for path in roles.glob('*/tasks/*.yml'):
                self.edit(roles, path.relative_to(roles), add_tasks)
            def add_harmless_assertion(tasks):
                transaction = next(task for task in tasks if 'block' in task)
                transaction['block'].insert(0, {'ansible.builtin.assert': {'that': ['true']}})
                for task in transaction['block']:
                    if 'ansible.builtin.assert' in task:
                        task['ansible.builtin.assert']['that'].append('true')
            self.edit(roles, 'restic/tasks/execute.yml', add_harmless_assertion)

        result = self.run_contracts(mutate)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_unsafe_restore_changes_are_rejected(self):
        def find(tasks, module, predicate=lambda args: True):
            return next(task for task in tasks if module in task and predicate(task[module]))

        def remove_cleanup(tasks):
            transaction = next(task for task in tasks if 'always' in task)
            transaction['always'].pop()

        def reorder_restore(tasks):
            transaction = next(task for task in tasks if 'block' in task)
            prepare = find(transaction['block'], 'ansible.builtin.include_tasks', lambda value: value == 'execute_prepare_app.yml')
            transaction['block'].remove(prepare)
            transaction['block'].append(prepare)

        mutations = [
            ('talos/tasks/generate.yml', remove_cleanup),
            ('restic/tasks/execute.yml', reorder_restore),
            ('restic/tasks/execute_prepare_app.yml', lambda tasks: find(tasks, 'kubernetes.core.k8s_exec').update(loop='{{ unsafe_paths }}')),
            ('restic/tasks/execute_restore_app.yml', lambda tasks: find(tasks, 'kubernetes.core.k8s_exec')['kubernetes.core.k8s_exec'].update(command='restic restore latest --target /')),
            ('restic/tasks/execute_resume_app.yml', lambda tasks: find(tasks, 'kubernetes.core.k8s_scale')['kubernetes.core.k8s_scale'].update(replicas=1)),
        ]
        for source, mutate in mutations:
            with self.subTest(source=source):
                result = self.run_contracts(lambda roles: self.edit(roles, source, mutate))
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
