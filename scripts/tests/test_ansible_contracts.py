"""Mutations of real role tasks: executable guards must survive harmless edits."""
import copy
from pathlib import Path
import sys
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_ansible_contracts import check_roles, check_changedetection

ROOT = Path(__file__).resolve().parents[2]


class AnsibleContractsTest(unittest.TestCase):
    def setUp(self):
        self.docs = {
            str(path.relative_to(ROOT / 'ansible/roles')): yaml.safe_load(path.read_text())
            for path in (ROOT / 'ansible/roles').glob('*/tasks/*.yml')
        }

    def tasks(self, path):
        return self.docs[path + '.yml']

    def rejected(self, expected):
        self.assertTrue(any(expected in error for error in check_roles(self.docs)),
                        check_roles(self.docs))

    def test_repository_passes(self):
        self.assertEqual(check_roles(self.docs), [])

    def test_one_terraform_task_loses_no_log(self):
        self.tasks('tofu/tasks/plan')[0].pop('no_log')
        self.rejected('no_log')

    def test_explicit_false_overrides_inherited_no_log(self):
        self.tasks('talos/tasks/generate')[1]['block'][2]['no_log'] = False
        self.rejected('no_log')

    def test_new_secret_use_needs_protection(self):
        self.tasks('tofu/tasks/plan').append({'ansible.builtin.debug': {'msg': '{{ tofu_bws_access_token }}'}})
        self.rejected('no_log')

    def test_sensitive_module_selector_cannot_disappear(self):
        self.tasks('tofu/tasks/apply').pop()
        self.rejected('Terraform')

    def test_check_mode_guards_each_mutation(self):
        self.tasks('talos/tasks/apply')[-1].pop('when')
        self.rejected('check mode')

    def test_inverted_check_mode_guard(self):
        self.tasks('talos/tasks/reset')[-1]['when'] = 'ansible_check_mode'
        self.rejected('check mode')

    def test_temporary_cleanup_must_be_in_always(self):
        block = self.tasks('talos/tasks/generate')[1]
        block['block'].append(block['always'].pop())
        self.rejected('always')

    def test_cleanup_explicit_no_log_false_is_rejected(self):
        self.tasks('talos/tasks/generate')[1]['always'][0]['no_log'] = False
        self.rejected('no_log')

    def test_warmup_cleanup_must_be_in_always(self):
        block = self.tasks('platform/tasks/k8tz_warmup')[-1]
        block['block'].extend(block.pop('always'))
        self.rejected('warmup')

    def test_native_wait_is_on_wait_operation(self):
        self.tasks('platform/tasks/wait_condition')[0]['kubernetes.core.k8s_info']['wait'] = False
        self.rejected('native wait')

    def test_deletion_failure_masking(self):
        self.tasks('platform/tasks/destroy')[0]['failed_when'] = False
        self.rejected('failure')

    def test_restore_resume_cannot_precede_data_restore(self):
        block = self.tasks('restic/tasks/execute')[-1]['block']
        indices = [i for i, task in enumerate(block) if 'ansible.builtin.include_tasks' in task]
        a, b = indices[-2:]
        block[a], block[b] = block[b], block[a]
        self.rejected('prepare')

    def test_stale_pod_selector_is_bounded(self):
        self.tasks('restic/tasks/execute')[2]['kubernetes.core.k8s_info']['label_selectors'] = []
        self.rejected('stale')

    def test_applicationset_assertion_cannot_disappear(self):
        block = self.tasks('restic/tasks/execute')[-1]['block']
        block[:] = [task for task in block if 'ansible.builtin.assert' not in task]
        self.rejected('ApplicationSet')

    def test_restore_flags_must_have_correct_values(self):
        task = self.tasks('restic/tasks/execute_restore_app')[0]['kubernetes.core.k8s_exec']
        task['command'] = task['command'].replace('restic_restore_snapshot_host', 'restic_restore_snapshot_tag')
        self.rejected('restore command')

    def test_restore_includes_must_be_planned_paths(self):
        task = self.tasks('restic/tasks/execute_restore_app')[0]['kubernetes.core.k8s_exec']
        task['command'] = task['command'].replace('restic_restore_app_plan.pvc_paths', "['/']")
        self.rejected('restore command')

    def test_prepare_scales_to_zero(self):
        self.tasks('restic/tasks/execute_prepare_app')[1]['kubernetes.core.k8s_scale']['replicas'] = 1
        self.rejected('scale')

    def test_delete_path_guard_rejects_root(self):
        self.tasks('restic/tasks/execute_prepare_app')[2]['ansible.builtin.assert']['that'] = ['true']
        self.rejected('delete path')

    def test_resume_uses_recorded_replicas(self):
        self.tasks('restic/tasks/execute_resume_app')[0]['kubernetes.core.k8s_scale']['replicas'] = 1
        self.rejected('replicas')

    def test_rescue_cannot_resume(self):
        self.tasks('restic/tasks/execute')[-1]['rescue'].insert(0, {'ansible.builtin.include_tasks': 'execute_resume_app.yml'})
        self.rejected('rescue')

    def test_rescue_cannot_delete_job(self):
        transaction = self.tasks('restic/tasks/execute')[-1]
        transaction['rescue'].insert(0, copy.deepcopy(transaction['block'][-1]))
        self.rejected('rescue')

    def test_always_cannot_resume_on_failure(self):
        self.tasks('restic/tasks/execute')[-1]['always'] = [{'ansible.builtin.include_tasks': 'execute_resume_app.yml'}]
        self.rejected('rescue')

    def test_terraform_credential_assertion_checks_each_credential(self):
        self.tasks('tofu/tasks/plan')[0]['ansible.builtin.assert']['that'] = ['true']
        self.rejected('credential')

    def test_terraform_environment_uses_protected_credentials(self):
        self.tasks('tofu/tasks/apply')[-1]['environment']['AWS_SECRET_ACCESS_KEY'] = 'literal'
        self.rejected('credential')

    def test_success_job_cleanup_cannot_precede_resume(self):
        block = self.tasks('restic/tasks/execute')[-1]['block']
        block.insert(0, block.pop())
        self.rejected('successful')

    def test_replica_restore_targets_original_workloads(self):
        self.tasks('restic/tasks/execute_resume_app')[0]['kubernetes.core.k8s_scale']['name'] = 'wrong-workload'
        self.rejected('workload')

    def test_applicationset_original_policy_not_replaced_with_default(self):
        block = self.tasks('restic/tasks/execute')[-1]['block']
        capture = next(task for task in block if 'restic_restore_applicationset_original_sync_policy' in task.get('ansible.builtin.set_fact', {}))
        capture['ansible.builtin.set_fact']['restic_restore_applicationset_original_sync_policy'] = {}
        self.rejected('original policy')

    def test_bootstrap_external_secrets_requires_cert_manager_first(self):
        tasks = self.tasks('platform/tasks/bootstrap')
        external = next(task for task in tasks if task.get('ansible.builtin.import_tasks') == 'external_secrets.yml')
        tasks.remove(external)
        tasks.insert(0, external)
        self.rejected('bootstrap dependency')

    def test_rescue_inherits_no_log_but_can_override_it(self):
        self.docs['tofu/tasks/example.yml'] = [{'no_log': True, 'block': [], 'rescue': [
            {'ansible.builtin.debug': {'msg': '{{ tofu_bws_access_token }}'}}]}]
        self.assertEqual(check_roles(self.docs), [])
        self.docs['tofu/tasks/example.yml'][0]['rescue'][0]['no_log'] = False
        self.rejected('no_log')

    def test_names_comments_and_extra_cleanup_are_harmless(self):
        def rename(tasks):
            for task in tasks:
                task['name'] = 'Unrelated wording with kubectl and failed_when: false'
                for branch in ('block', 'rescue', 'always'):
                    rename(task.get(branch, []))
        for tasks in self.docs.values():
            rename(tasks)
        self.tasks('talos/tasks/generate')[1]['always'].append({'ansible.builtin.debug': {'msg': 'cleanup finished'}})
        self.tasks('platform/tasks/k8tz_warmup')[-1]['always'].append({'ansible.builtin.debug': {'msg': 'cleanup finished'}})
        self.assertEqual(check_roles(self.docs), [])


class ChangedetectionContractTest(unittest.TestCase):
    def setUp(self):
        app = ROOT / 'apps/selfhosted/changedetection'
        self.values = yaml.safe_load((app / 'values.yaml').read_text())
        self.secret = yaml.safe_load((app / 'manifests/changedetection-credentials.externalsecret.yaml').read_text())

    def test_model_and_input_size_are_choices(self):
        env = self.values['controllers']['main']['containers']['app']['env']
        env['LLM_MODEL'] = 'another-model'
        env['LLM_MAX_INPUT_CHARS'] = '8192'
        self.assertEqual(check_changedetection(self.values, self.secret), [])

    def test_wrong_credential_reference_fails(self):
        self.secret['spec']['data'][1]['remoteRef']['key'] = 'wrong-key'
        self.assertTrue(check_changedetection(self.values, self.secret))

    def test_unused_secret_fails(self):
        self.values['controllers']['main']['containers']['app']['envFrom'] = []
        self.assertTrue(check_changedetection(self.values, self.secret))

    def test_empty_model_and_nonpositive_limit_fail(self):
        env = self.values['controllers']['main']['containers']['app']['env']
        for key, value in [('LLM_MODEL', ''), ('LLM_MAX_INPUT_CHARS', '0')]:
            with self.subTest(key=key):
                saved = env[key]
                env[key] = value
                self.assertTrue(check_changedetection(self.values, self.secret))
                env[key] = saved


if __name__ == '__main__':
    unittest.main()
