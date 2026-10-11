import os
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from test_secrets import ROOT, module


class DeliveryPredicates(unittest.TestCase):
    def setUp(self):
        self.delivery = module('secret_delivery')

    def test_root_requires_every_source_revision_and_sync(self):
        root = {'spec': {'sources': [{}, {}]}, 'status': {'sync': {'status': 'Synced', 'revisions': ['new', 'new']}}}
        self.assertTrue(self.delivery.platform_root_ready(root, 'new'))
        root['status']['sync']['revisions'][1] = 'old'
        self.assertFalse(self.delivery.platform_root_ready(root, 'new'))
        root['status']['sync']['revisions'] = ['new']
        self.assertFalse(self.delivery.platform_root_ready(root, 'new'))
        root['status']['sync']['revisions'] = ['new', 'new']
        root['status']['sync']['status'] = 'OutOfSync'
        self.assertFalse(self.delivery.platform_root_ready(root, 'new'))

    def test_ready_requires_fresh_valid_timestamp(self):
        now = datetime.now(timezone.utc)
        resource = {'status': {'refreshTime': '2000-01-01T00:00:00Z', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        self.assertFalse(self.delivery.platform_secret_ready(resource, now.timestamp()))
        resource['status']['refreshTime'] = now.isoformat()
        self.assertTrue(self.delivery.platform_secret_ready(resource, now.timestamp()))
        resource['status']['refreshTime'] = 'invalid'
        self.assertFalse(self.delivery.platform_secret_ready(resource, now.timestamp()))
        resource['status']['refreshTime'] = now.isoformat()
        resource['status']['conditions'][0]['status'] = 'False'
        self.assertFalse(self.delivery.platform_secret_ready(resource, now.timestamp()))

    def test_provider_json_parser_never_surfaces_malformed_payload(self):
        self.assertIsNone(self.delivery.safe_from_json('PRIVATE_PROVIDER_DIAGNOSTIC'))
        self.assertEqual(self.delivery.safe_from_json('[{"id":"fixture"}]'), [{'id': 'fixture'}])

    def test_only_children_owned_by_expected_appset_count(self):
        resources = [{'metadata': {'name': 'child', 'ownerReferences': [{'uid': 'expected'}]}}, {'metadata': {'name': 'unrelated', 'ownerReferences': [{'uid': 'other'}]}}]
        self.assertEqual(self.delivery.platform_owned_applications(resources, 'expected'), ['child'])


class NativeLauncher(unittest.TestCase):
    def test_task_clears_inherited_credentials_and_preserves_operator_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            record = path / 'record.json'
            stub = path / 'secretspec'
            stub.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
pathlib.Path(os.environ['FIXTURE_RECORD']).write_text(json.dumps({'environment':dict(os.environ),'args':sys.argv[1:]}))
''')
            stub.chmod(0o755)
            validator = path / 'ansible-playbook'
            validator.write_text('#!/bin/sh\nexit 0\n')
            validator.chmod(0o755)
            stale = {'BWS_ACCESS_TOKEN': 'PRIVATE', 'BW_ACCESS_TOKEN': 'PRIVATE', 'AWS_ACCESS_KEY_ID': 'PRIVATE', 'AWS_SECRET_ACCESS_KEY': 'PRIVATE', 'AWS_SESSION_TOKEN': 'PRIVATE', 'TF_VAR_cloudflare_api_token': 'PRIVATE', 'TF_CLI_ARGS_plan': 'PRIVATE', 'ANSIBLE_VAULT_PASSWORD_FILE': 'PRIVATE', 'SECRETSPEC_PROVIDER': 'env', 'TALOS_SECRETS_YAML': 'PRIVATE', 'ESO_BWS_ACCESS_TOKEN': 'PRIVATE'}
            env = dict(os.environ, **stale)
            env.update(HOME=str(path), PATH=str(path)+os.pathsep+os.environ['PATH'], TALOS_NODE='192.0.2.10', TALOSCONFIG='custom path/config', FIXTURE_RECORD=str(record))
            result = subprocess.run(['task', 'secrets:check', 'scope=talos', 'ANSIBLE_PLAYBOOK='+str(validator)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            delivered = json.loads(record.read_text())
            self.assertTrue(all(name not in delivered['environment'] for name in stale))
            self.assertEqual(delivered['environment']['TALOS_NODE'], '192.0.2.10')
            self.assertEqual(delivered['environment']['TALOSCONFIG'], 'custom path/config')
            self.assertEqual(delivered['args'][delivered['args'].index('--scope')+1], 'talos')
            self.assertEqual(delivered['environment']['SECRETSPEC_BWS_CLI_PATH'], str(ROOT/'ansible/roles/operator_secrets/files/bws_readonly.py'))
            self.assertNotIn('PRIVATE', ' '.join(delivered['args']))
            record.unlink()
            validator.write_text('#!/bin/sh\nexit 1\n')
            result = subprocess.run(['task', 'secrets:check', 'scope=talos', 'ANSIBLE_PLAYBOOK='+str(validator)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(record.exists(), 'A failed Ansible preflight must prevent SecretSpec invocation')
