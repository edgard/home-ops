#!/usr/bin/env python3
"""Offline structural and rendered-command contracts for destructive Ansible roles.

Task names/comments are not contracts. Conditions and command arguments are rendered
with Ansible using inert fixture values; no role or external command is executed.
"""
import argparse
from pathlib import Path
import re
import shlex

from ansible.template import Templar, trust_as_template
import yaml


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def render(value, variables):
    if isinstance(value, str):
        return Templar(variables=variables).template(trust_as_template(value))
    if isinstance(value, list):
        return [render(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render(item, variables) for key, item in value.items()}
    return value


def conditions(value, variables):
    values = value if isinstance(value, list) else [value]
    templar = Templar(variables=variables)
    return all(templar.evaluate_expression(trust_as_template(item))
               if isinstance(item, str) else bool(item) for item in values)


def walk(tasks, inherited_log=False, inherited_when=(), branch='tasks'):
    for index, task in enumerate(tasks):
        path = f'{branch}[{index}]'
        no_log = task.get('no_log', inherited_log)
        when = task.get('when', [])
        when = when if isinstance(when, list) else [when]
        guards = [*inherited_when, *when]
        yield task, no_log, guards, path
        for child in ('block', 'rescue', 'always'):
            yield from walk(task.get(child, []), no_log, guards, f'{path}.{child}')


def module_tasks(tasks, module):
    return [task for task, _, _, _ in walk(tasks) if module in task]


def only(tasks, module, predicate=lambda args: True):
    matches = [task for task in module_tasks(tasks, module) if predicate(task[module])]
    require(len(matches) == 1, f'expected one {module} operation, found {len(matches)}')
    return matches[0]


def no_failure_mask(task):
    require('failed_when' not in task and not task.get('ignore_errors'),
            'deletion/wait failure must propagate')


def check_sensitive(docs):
    errors = []
    secrets = re.compile(r'\b(?:tofu_(?:aws_access_key_id|aws_secret_access_key|bws_access_token)|platform_bitwarden_access_token|talos_(?:secrets_file|generate_secrets_temp|generate_output))\b')
    for filename, tasks in docs.items():
        for task, protected, _, path in walk(tasks):
            args = {key: value for key, value in task.items()
                    if key not in ('name', 'block', 'rescue', 'always', 'no_log')}
            sensitive = secrets.search(str(args)) or 'community.general.terraform' in task
            if filename == 'talos/tasks/generate.yml' and any(key in task for key in
                    ('ansible.builtin.command', 'ansible.builtin.copy', 'ansible.builtin.tempfile', 'ansible.builtin.file')):
                sensitive = True
            definition = task.get('kubernetes.core.k8s', {}).get('definition', {})
            sensitive = sensitive or (isinstance(definition, dict) and definition.get('kind') == 'Secret')
            if sensitive and render(protected, {}) is not True:
                errors.append(f'{filename}:{path}: sensitive task requires effective no_log: true')
    for filename in ('tofu/tasks/plan.yml', 'tofu/tasks/apply.yml'):
        tasks = docs[filename]
        if not module_tasks(tasks, 'community.general.terraform') or not module_tasks(tasks, 'ansible.builtin.assert'):
            errors.append(f'{filename}: Terraform module and credential assertion must exist')
    if not any(task['kubernetes.core.k8s'].get('definition', {}).get('kind') == 'Secret'
               for task in module_tasks(docs['platform/tasks/external_secrets.yml'], 'kubernetes.core.k8s')):
        errors.append('Bitwarden Secret creation must exist')
    if not module_tasks(docs['talos/tasks/generate.yml'], 'ansible.builtin.command'):
        errors.append('Talos generation command must exist')
    return errors


def check_credentials(docs):
    fixture = {'tofu_aws_access_key_id': 'fixture-key', 'tofu_aws_secret_access_key': 'fixture-secret',
               'tofu_bws_access_token': 'fixture-token'}
    for filename in ('tofu/tasks/plan.yml', 'tofu/tasks/apply.yml'):
        assertion = only(docs[filename], 'ansible.builtin.assert')['ansible.builtin.assert']['that']
        require(conditions(assertion, fixture), 'Terraform credential assertions must accept supplied credentials')
        for key in fixture:
            require(not conditions(assertion, {**fixture, key: ''}), f'Terraform credential assertion must reject empty {key}')
        task = only(docs[filename], 'community.general.terraform')
        require(render(task.get('environment'), fixture) == {
            'AWS_ACCESS_KEY_ID': 'fixture-key', 'AWS_SECRET_ACCESS_KEY': 'fixture-secret',
            'BWS_ACCESS_TOKEN': 'fixture-token', 'BW_ACCESS_TOKEN': 'fixture-token'},
            'Terraform environment must use the protected credentials')
    task = only(docs['platform/tasks/external_secrets.yml'], 'kubernetes.core.k8s',
                lambda args: args.get('definition', {}).get('kind') == 'Secret')
    secret = task['kubernetes.core.k8s']['definition']
    require(secret['metadata'] == {'name': 'bitwarden-credentials', 'namespace': 'platform-system'}
            and render(secret['stringData'], {'platform_bitwarden_access_token': 'fixture-token'}) == {'token': 'fixture-token'},
            'Bitwarden Secret must receive the protected credential')


def check_talos(docs):
    fixture = {'talos_upgrade_test_mode': False, 'talos_upgrade_kubernetes_node': 'node',
               'talos_generate_secrets_temp': {'path': '/tmp/secrets'},
               'talos_generate_output': {'path': '/tmp/output'}}
    for filename, tasks in docs.items():
        if not filename.startswith('talos/tasks/'):
            continue
        for task, _, guards, path in walk(tasks):
            if any(module in task for module in ('ansible.builtin.command', 'ansible.builtin.shell',
                    'ansible.builtin.copy', 'ansible.builtin.file', 'ansible.builtin.tempfile', 'kubernetes.core.k8s')):
                require(not conditions(guards, {**fixture, 'ansible_check_mode': True})
                        and conditions(guards, {**fixture, 'ansible_check_mode': False}),
                        f'{filename}:{path}: mutation must be skipped in check mode and enabled normally')
    tasks = docs['talos/tasks/generate.yml']
    blocks = [task for task, _, _, _ in walk(tasks) if 'block' in task]
    require(blocks, 'Talos temporary cleanup must use always')
    registrations = module_tasks(tasks, 'ansible.builtin.tempfile')
    require(registrations, 'Talos tempfile registrations must exist')
    for registration in registrations:
        key = registration.get('register')
        require(key, 'Talos tempfile must register its path')
        enclosing = [block for block in blocks if registration in module_tasks(block['block'], 'ansible.builtin.tempfile')]
        cleanup = [task for block in enclosing for task in module_tasks(block.get('always', []), 'ansible.builtin.file')
                   if task['ansible.builtin.file'].get('state') == 'absent']
        require(any(render(task['ansible.builtin.file']['path'], fixture) == fixture[key]['path']
                    and conditions(task.get('when', []), fixture)
                    and not conditions(task.get('when', []), {k: v for k, v in fixture.items() if k != key})
                    for task in cleanup), f'Talos {key} must have guarded cleanup in always')


def check_platform(docs):
    warmup = docs['platform/tasks/k8tz_warmup.yml']
    block = next(task for task in warmup if 'block' in task)
    creation = only(block['block'], 'kubernetes.core.k8s', lambda args: args.get('state') == 'present')
    metadata = creation['kubernetes.core.k8s']['definition']['metadata']
    require(any(task['kubernetes.core.k8s'].get('state') == 'absent'
                and task['kubernetes.core.k8s'].get('kind') == 'Pod'
                and task['kubernetes.core.k8s'].get('name') == metadata['name']
                and task['kubernetes.core.k8s'].get('namespace') == metadata['namespace']
                and task['kubernetes.core.k8s'].get('wait') is True
                for task in module_tasks(block.get('always', []), 'kubernetes.core.k8s')),
            'warmup Pod must be removed in always')
    waits = module_tasks(docs['platform/tasks/wait_condition.yml'], 'kubernetes.core.k8s_info')
    require(waits, 'platform native wait operation must exist')
    for task in waits:
        args = task['kubernetes.core.k8s_info']
        require(args.get('wait') is True and args.get('wait_condition', {}).get('type')
                and args.get('wait_sleep') and args.get('wait_timeout') and 'until' not in task,
                'platform operation must use native wait with condition, sleep and timeout')
        no_failure_mask(task)
    deletions = module_tasks(docs['platform/tasks/destroy.yml'], 'kubernetes.core.k8s')
    require(deletions, 'platform deletion must exist')
    for task in deletions:
        no_failure_mask(task)
        require(task['kubernetes.core.k8s'].get('state') == 'absent' and task['kubernetes.core.k8s'].get('wait') is True,
                'platform deletion must wait')


def check_bootstrap(docs):
    tasks = docs['platform/tasks/bootstrap.yml']
    fixture = {'platform_bootstrap_release_specs': [
        {'name': 'fixture-storage', 'phase': 'storage'},
        {'name': 'fixture-network', 'phase': 'networking'},
        {'name': 'fixture-cert', 'phase': 'certificates'},
        {'name': 'fixture-secrets', 'phase': 'external-secrets'},
        {'name': 'fixture-argo', 'phase': 'argocd'}]}
    foundations = only(tasks, 'ansible.builtin.include_tasks', lambda path: path == 'install_release_with_manifests.yml')
    certificates = only(tasks, 'ansible.builtin.include_tasks', lambda path: path == 'install_release.yml')
    external = only(tasks, 'ansible.builtin.import_tasks', lambda path: path == 'external_secrets.yml')
    argo = only(tasks, 'ansible.builtin.import_tasks', lambda path: path == 'argocd.yml')
    require(tasks.index(foundations) < tasks.index(certificates) < tasks.index(external) < tasks.index(argo),
            'bootstrap dependency order must install foundations, certificates, secrets, then Argo CD')
    require([item['phase'] for item in render(foundations.get('loop'), fixture)] == ['storage', 'networking']
            and render(certificates['vars']['platform_release_spec'], fixture)['phase'] == 'certificates',
            'bootstrap dependency operations must select the required release phases')


def restore_fixture():
    return {
        'restic_restore_job_name': 'fixture-restore-job', 'restic_restore_namespace': 'fixture-ns',
        'restic_restore_argocd_namespace': 'fixture-argocd', 'restic_restore_applicationset_name': 'fixture-appset',
        'restic_restore_retry_lock': '17s', 'restic_restore_effective_snapshot': 'fixture-snapshot',
        'restic_restore_snapshot_host': 'fixture-host', 'restic_restore_snapshot_tag': 'fixture-tag',
        'restic_restore_snapshot_path': '/data/appdata', 'restic_restore_target_root': '/restore',
        'restic_restore_app_plan': {'app': 'fixture-app', 'had_automated_sync': True, 'had_sync_policy': True,
                                    'sync_policy': {'automated': {'prune': False}},
                                    'pvc_paths': ['/data/appdata/ns/a', '/data/appdata/ns/b'],
                                    'restore_paths': ['/restore/data/appdata/ns/a', '/restore/data/appdata/ns/b'],
                                    'workloads': [{'replicas': 3, 'name': 'fixture-workload'}]},
        'restic_restore_applicationset_info': {'resources': [{'spec': {'syncPolicy': {'applicationsSync': 'sync'}}}]},
        'restic_restore_applicationset_had_sync_policy': True,
        'restic_restore_applicationset_original_sync_policy': {'applicationsSync': 'sync'},
        'item': {'metadata': {'name': 'fixture-pod'}, 'replicas': 3, 'api_version': 'apps/v1', 'kind': 'Deployment', 'namespace': 'fixture-app-ns', 'name': 'fixture-workload'},
        'restic_restore_stale_pods': {'resources': [{'metadata': {'name': 'fixture-pod'}}]},
    }


def check_restore(docs):
    fixture = restore_fixture()
    tasks = docs['restic/tasks/execute.yml']
    transaction = next(task for task in tasks if 'block' in task)
    block = transaction['block']
    # Fail closed: a destructive failure leaves the job and pause state inspectable.
    rescue = [task for task, _, _, _ in walk(transaction.get('rescue', []))]
    require(any('ansible.builtin.fail' in task for task in rescue), 'restore rescue must fail')
    for task in [*rescue, *(task for task, _, _, _ in walk(transaction.get('always', [])))]:
        require(all(key in ('name', 'ansible.builtin.fail', 'ansible.builtin.debug') for key in task),
                'restore rescue/always must not resume workloads or delete inspection state')
    includes = [task for task in block if 'ansible.builtin.include_tasks' in task]
    require([task['ansible.builtin.include_tasks'] for task in includes] ==
            ['execute_prepare_app.yml', 'execute_restore_app.yml', 'execute_resume_app.yml'],
            'restore transaction requires prepare → restore → resume order')
    for task in includes:
        require(task.get('loop') == '{{ restic_restore_plan }}' and task.get('loop_control', {}).get('loop_var') == 'restic_restore_app_plan',
                'prepare/restore/resume must use the same plan')
    stale = tasks[:tasks.index(transaction)]
    pod_lookup = only(stale, 'kubernetes.core.k8s_info', lambda args: args.get('kind') == 'Pod')
    lookup = pod_lookup['kubernetes.core.k8s_info']
    require(render(lookup.get('label_selectors'), fixture) == ['job-name=fixture-restore-job']
            and render(lookup.get('namespace'), fixture) == 'fixture-ns', 'stale Pod lookup must be bounded to restore Job')
    for kind in ('Job', 'Pod'):
        deletion = only(stale, 'kubernetes.core.k8s', lambda args: args.get('kind') == kind)
        args = deletion['kubernetes.core.k8s']
        require(args.get('state') == 'absent' and args.get('wait') is True
                and render(args.get('namespace'), fixture) == 'fixture-ns'
                and render(args.get('name'), fixture) == ('fixture-restore-job' if kind == 'Job' else 'fixture-pod'),
                'stale deletion must be bounded and wait')
        no_failure_mask(deletion)
        if kind == 'Pod':
            require(render(deletion.get('loop'), fixture) == fixture['restic_restore_stale_pods']['resources'],
                    'stale Pod deletion must use lookup results')
    appset_read = only(block, 'kubernetes.core.k8s_info', lambda args: args.get('kind') == 'ApplicationSet')
    assertions = module_tasks(block, 'ansible.builtin.assert')
    require(any(conditions(task['ansible.builtin.assert']['that'], fixture)
                and not conditions(task['ansible.builtin.assert']['that'], {**fixture, 'restic_restore_applicationset_info': {'resources': []}})
                and block.index(appset_read) < block.index(task) < block.index(includes[0])
                for task in assertions), 'ApplicationSet existence must be asserted before pause')
    pause = only(block, 'kubernetes.core.k8s', lambda args: args.get('definition', {}).get('spec', {}).get('syncPolicy') == {'applicationsSync': 'create-only'})
    require(all(block.index(task) < block.index(pause) for task in assertions), 'ApplicationSet assertion must precede pause')
    captures = module_tasks(block, 'ansible.builtin.set_fact')
    policy_capture = next((task for task in captures if 'restic_restore_applicationset_original_sync_policy' in task['ansible.builtin.set_fact']), None)
    require(policy_capture is not None and block.index(policy_capture) < block.index(pause), 'ApplicationSet original policy must be captured before pause')
    require(render(policy_capture['ansible.builtin.set_fact'], fixture) == {
        'restic_restore_applicationset_had_sync_policy': True,
        'restic_restore_applicationset_original_sync_policy': {'applicationsSync': 'sync'}}, 'ApplicationSet capture must retain original policy')
    restoration = only(block, 'kubernetes.core.k8s', lambda args: args.get('definition', {}).get('spec', {}).get('syncPolicy') == '{{ restic_restore_applicationset_original_sync_policy }}')
    removal = only(block, 'kubernetes.core.k8s_json_patch')
    require(block.index(pause) < block.index(includes[0]) and block.index(restoration) > block.index(includes[-1]), 'ApplicationSet pause and restoration order')
    require(conditions(restoration.get('when', []), fixture) and not conditions(restoration.get('when', []), {**fixture, 'restic_restore_applicationset_had_sync_policy': False})
            and not conditions(removal.get('when', []), fixture) and conditions(removal.get('when', []), {**fixture, 'restic_restore_applicationset_had_sync_policy': False})
            and removal['kubernetes.core.k8s_json_patch'].get('patch') == [{'op': 'remove', 'path': '/spec/syncPolicy'}],
            'ApplicationSet original policy presence must be restored')
    success_cleanup = only(block, 'kubernetes.core.k8s', lambda args: args.get('kind') == 'Job' and args.get('state') == 'absent')
    require(block.index(success_cleanup) > max(block.index(includes[-1]), block.index(restoration), block.index(removal))
            and render(success_cleanup['kubernetes.core.k8s'].get('name'), fixture) == 'fixture-restore-job'
            and render(success_cleanup['kubernetes.core.k8s'].get('namespace'), fixture) == 'fixture-ns'
            and success_cleanup['kubernetes.core.k8s'].get('wait') is True,
            'successful restore Job cleanup must follow resume and policy restoration')
    no_failure_mask(success_cleanup)
    prepare = docs['restic/tasks/execute_prepare_app.yml']
    scale = only(prepare, 'kubernetes.core.k8s_scale')
    pause_app = only(prepare, 'kubernetes.core.k8s_json_patch')
    deletion = only(prepare, 'kubernetes.core.k8s_exec')
    guard = only(prepare, 'ansible.builtin.assert')
    require(prepare.index(pause_app) < prepare.index(scale) < prepare.index(guard) < prepare.index(deletion)
            and scale['kubernetes.core.k8s_scale'].get('replicas') == 0
            and scale['kubernetes.core.k8s_scale'].get('wait') is True, 'app pause and scale to zero must precede deletion')
    require(pause_app['kubernetes.core.k8s_json_patch'].get('patch') == [{'op': 'remove', 'path': '/spec/syncPolicy/automated'}], 'app automated sync must pause')
    require(conditions(pause_app.get('when', []), fixture) and not conditions(pause_app.get('when', []), {**fixture, 'restic_restore_app_plan': {**fixture['restic_restore_app_plan'], 'had_automated_sync': False}}), 'app pause must respect recorded automated sync')
    for path, allowed in [('/restore/data/appdata/ns/pvc', True), ('/', False), ('/restore', False), ('/restore/data/appdata/', False), ('/data/appdata/ns/pvc', False)]:
        require(conditions(guard['ansible.builtin.assert']['that'], {'item': path}) == allowed, 'restore delete path guard must reject unsafe roots')
    require(render(guard.get('loop'), fixture) == fixture['restic_restore_app_plan']['restore_paths']
            and render(deletion.get('loop'), fixture) == fixture['restic_restore_app_plan']['restore_paths'], 'delete path guard and deletion must use planned restore paths')
    delete_path = '/restore/data/appdata/ns/pvc'
    command = shlex.split(render(deletion['kubernetes.core.k8s_exec']['command'], {'item': delete_path}))
    require(len(command) == 3 and command[:2] == ['sh', '-ceu'],
            'delete path command must fail on shell errors')
    require(shlex.split(command[2]) == [
        'if', '[', '-d', delete_path, '];', 'then', 'find', delete_path,
        '-mindepth', '1', '-maxdepth', '1', '-exec', 'rm', '-rf', '--', '{}', '+;',
        'else', 'mkdir', '-p', delete_path + ';', 'fi'],
        'delete path command must only remove children of the guarded PVC directory')
    restore = only(docs['restic/tasks/execute_restore_app.yml'], 'kubernetes.core.k8s_exec')
    argv = shlex.split(render(restore['kubernetes.core.k8s_exec']['command'], fixture))
    expected = ['restic', '--retry-lock', '17s', 'restore', 'fixture-snapshot', '--host', 'fixture-host', '--tag', 'fixture-tag',
                '--path', '/data/appdata', '--include', '/data/appdata/ns/a', '--include', '/data/appdata/ns/b', '--exclude-xattr', '*', '--target', '/restore']
    require(argv == expected, 'restore command must pair snapshot selectors, include paths and target with configured values')
    resume = docs['restic/tasks/execute_resume_app.yml']
    scale_up = only(resume, 'kubernetes.core.k8s_scale')
    require(render(scale_up['kubernetes.core.k8s_scale']['replicas'], fixture) == 3
            and render(scale_up.get('loop'), fixture) == fixture['restic_restore_app_plan']['workloads']
            and scale_up['kubernetes.core.k8s_scale'].get('wait') is True, 'resume must restore recorded replicas and wait')
    for task in (scale, scale_up):
        args = task['kubernetes.core.k8s_scale']
        require(all(render(args.get(key), fixture) == fixture['item'][key]
                    for key in ('api_version', 'kind', 'namespace', 'name'))
                and render(task.get('loop'), fixture) == fixture['restic_restore_app_plan']['workloads'],
                'scale operations must target the recorded workloads')
        no_failure_mask(task)
    app_policy = only(resume, 'kubernetes.core.k8s')
    require(render(app_policy['kubernetes.core.k8s']['definition']['spec']['syncPolicy'], fixture) == fixture['restic_restore_app_plan']['sync_policy']
            and conditions(app_policy.get('when', []), fixture)
            and not conditions(app_policy.get('when', []), {**fixture, 'restic_restore_app_plan': {**fixture['restic_restore_app_plan'], 'had_sync_policy': False}}), 'resume must restore original app policy')


def check_roles(documents):
    errors = check_sensitive(documents)
    for check in (check_credentials, check_talos, check_platform, check_bootstrap, check_restore):
        try:
            check(documents)
        except (ContractError, KeyError, StopIteration, TypeError, ValueError) as error:
            errors.append(f'{check.__name__}: {error}')
    for filename, tasks in documents.items():
        for task, _, _, path in walk(tasks):
            for module in ('ansible.builtin.command', 'ansible.builtin.shell'):
                if module in task and re.search(r'\bkubectl\b', str(task[module])):
                    errors.append(f'{filename}:{path}: use native Kubernetes modules')
    return errors


def check_changedetection(values, secret):
    try:
        app = values['controllers']['main']['containers']['app']
        env = app['env']
        spec = secret['spec']
        require(isinstance(env['LLM_MODEL'], str) and env['LLM_MODEL'].strip()
                and int(env['LLM_MAX_INPUT_CHARS']) > 0,
                'Changedetection requires a nonempty model and positive input limit')
        require('LLM_API_BASE' not in env and 'LLM_FEATURES_DISABLED' not in env,
                'Changedetection shared OpenAI integration must stay enabled')
        require(spec['target']['name'] in [item.get('secretRef', {}).get('name') for item in app['envFrom']]
                and spec['secretStoreRef'] == {'name': 'external-secrets-store', 'kind': 'ClusterSecretStore'}
                and spec['target']['template']['data']['LLM_API_KEY'] == '{{ .openai_api_key }}'
                and [item['remoteRef']['key'] for item in spec['data'] if item['secretKey'] == 'openai_api_key'] == ['openai_api_key'],
                'Changedetection must consume the shared OpenAI credential')
    except (ContractError, KeyError, TypeError, ValueError) as error:
        return [f'Changedetection: {error}']
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    role_root = args.root / 'ansible/roles'
    documents = {str(path.relative_to(role_root)): yaml.safe_load(path.read_text())
                 for path in role_root.glob('*/tasks/*.yml')}
    errors = check_roles(documents)
    app = args.root / 'apps/selfhosted/changedetection'
    errors.extend(check_changedetection(yaml.safe_load((app / 'values.yaml').read_text()),
                                        yaml.safe_load((app / 'manifests/changedetection-credentials.externalsecret.yaml').read_text())))
    for error in errors:
        print(error)
    if not errors:
        print('Ansible safety contracts passed')
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
