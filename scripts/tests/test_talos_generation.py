import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml
from test_secrets import ROOT

MATERIAL = yaml.safe_dump({'cluster': {'id': 'synthetic', 'secret': 'synthetic'}, 'secrets': {'bootstraptoken': 'synthetic', 'secretboxencryptionsecret': 'synthetic'}, 'trustdinfo': {'token': 'synthetic'}, 'certs': {name: {'crt': 'synthetic', 'key': 'synthetic'} for name in ('etcd', 'k8s', 'k8saggregator', 'k8sserviceaccount', 'os')}})


class TalosGenerationIntegration(unittest.TestCase):
    def generate(self, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            binary = fixture / 'talosctl'
            binary.write_text('''#!/usr/bin/env python3
import json,os,pathlib,stat,sys
args=sys.argv[1:]
if args[:2] == ['gen','config']:
    source=pathlib.Path(args[args.index('--with-secrets')+1])
    assert stat.S_IMODE(source.stat().st_mode) == 0o600
    record={'args':args,'secrets_path':str(source),'output_dir':args[args.index('--output-dir')+1]}
    pathlib.Path(os.environ['FIXTURE_RECORD']).write_text(json.dumps(record))
    if os.environ.get('FIXTURE_FAIL') == '1':
        print('PRIVATE_FAILURE_MATERIAL',file=sys.stderr)
        sys.exit(1)
    output=pathlib.Path(record['output_dir'])
    (output/'talosconfig').write_text('synthetic-config')
    (output/'controlplane.yaml').write_text('synthetic-controlplane')
''')
            binary.chmod(0o755)
            playbook = fixture / 'generate.yml'
            config = fixture / 'custom client/config'
            plane = fixture / 'custom machine/controlplane.yaml'
            playbook.write_text(yaml.safe_dump([{'name': 'Exercise generation', 'hosts': 'localhost', 'gather_facts': False, 'vars': {'repo_root': str(ROOT), 'ansible_python_interpreter': str(ROOT / '.venv/bin/python'), 'talos_node': '192.0.2.10', 'talos_cluster_name': 'fixture', 'talos_install_disk': '/dev/fixture', 'talos_config_path': str(config), 'talos_controlplane_config_path': str(plane)}, 'tasks': [{'name': 'Generate', 'ansible.builtin.include_role': {'name': 'talos', 'tasks_from': 'generate'}}]}]))
            record = fixture / 'record.json'
            env = dict(os.environ, PATH=str(fixture) + os.pathsep + os.environ['PATH'], TALOS_SECRETS_YAML=MATERIAL, FIXTURE_RECORD=str(record), FIXTURE_FAIL=str(int(fail)))
            for key in ('ANSIBLE_VAULT_PASSWORD', 'ANSIBLE_VAULT_PASSWORD_FILE', 'BWS_ACCESS_TOKEN', 'KUBECONFIG', 'TALOSCONFIG'):
                env.pop(key, None)
            result = subprocess.run([str(ROOT / '.venv/bin/ansible-playbook'), str(playbook)], env=env, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertNotIn('PRIVATE_FAILURE_MATERIAL', result.stdout + result.stderr)
            generated = json.loads(record.read_text())
            self.assertFalse(Path(generated['secrets_path']).exists())
            self.assertFalse(Path(generated['output_dir']).exists())
            if fail:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(config.exists())
                self.assertFalse(plane.exists())
            else:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(config.stat().st_mode & 0o777, 0o600)
                self.assertEqual(plane.stat().st_mode & 0o777, 0o600)
                self.assertEqual(config.parent.stat().st_mode & 0o777, 0o700)
                from bootstrap import generation_targets
                targets = generation_targets(ROOT)
                for flag, expected in (('--talos-version', targets['talos']), ('--kubernetes-version', targets['kubernetes']), ('--install-image', targets['installer'])):
                    self.assertEqual(generated['args'][generated['args'].index(flag) + 1], expected)

    def test_fresh_generation_custom_paths_and_versions(self):
        self.generate()

    def test_generation_failure_cleans_temporary_secrets(self):
        self.generate(fail=True)

    def test_cluster_preflight_denial_never_contacts_node(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            for name in ('bws', 'talosctl', 'helm'):
                binary = fixture / name
                binary.write_text('#!/bin/sh\necho PRIVATE_PROVIDER_ERROR >&2\nexit 1\n' if name == 'bws' else '#!/bin/sh\ntouch "$FIXTURE_NODE_CONTACT"\nexit 0\n')
                binary.chmod(0o755)
            marker = fixture / 'node-contact'
            env = dict(os.environ, PATH=str(fixture) + os.pathsep + os.environ['PATH'], TALOS_NODE='192.0.2.10', TALOS_CLUSTER_NAME='fixture', TALOS_INSTALL_DISK='/dev/fixture', TALOS_SECRETS_YAML=MATERIAL, ESO_BWS_ACCESS_TOKEN='synthetic', FIXTURE_NODE_CONTACT=str(marker))
            result = subprocess.run([str(ROOT / '.venv/bin/ansible-playbook'), 'ansible/playbooks/cluster-create.yml'], env=env, cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertNotIn('PRIVATE_PROVIDER_ERROR', result.stdout + result.stderr)
            self.assertIn('eso-project-access-failed', result.stdout)
