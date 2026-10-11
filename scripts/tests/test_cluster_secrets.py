import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from test_secrets import module


class HandoffTests(unittest.TestCase):
    def test_root_requires_expected_revision_and_sync(self):
        cluster = module('cluster_secrets')
        self.assertFalse(cluster.root_ready({'status': {'sync': {'status': 'Synced', 'revisions': ['old']}}}, 'new'))
        self.assertFalse(cluster.root_ready({'status': {'sync': {'status': 'OutOfSync', 'revisions': ['new']}}}, 'new'))
        self.assertTrue(cluster.root_ready({'spec': {'sources': [{}, {}]}, 'status': {'sync': {'status': 'Synced', 'revisions': ['new', 'new']}}}, 'new'))

    def test_old_external_secret_ready_does_not_prove_rotation(self):
        cluster = module('cluster_secrets')
        now = datetime.now(timezone.utc)
        resource = {'status': {'refreshTime': '2000-01-01T00:00:00Z', 'conditions': [{'type': 'Ready', 'status': 'True'}]}}
        self.assertFalse(cluster.secret_ready(resource, now))
        resource['status']['refreshTime'] = now.isoformat()
        self.assertTrue(cluster.secret_ready(resource, now))

    def test_invalid_token_prevents_secret_update(self):
        cluster = module('cluster_secrets')
        api = object()
        with patch.object(cluster, 'application_access', side_effect=RuntimeError('synthetic')), patch.object(cluster, 'replace_token') as replace:
            with self.assertRaises(RuntimeError):
                cluster.sync_token(api, 'invalid')
            replace.assert_not_called()

    def test_failed_rotation_restores_previous_token(self):
        cluster = module('cluster_secrets')
        with patch.object(cluster, 'application_access', return_value={}), patch.object(cluster, 'read_token', return_value='old'), patch.object(cluster, 'replace_token') as replace, patch.object(cluster, 'wait_secrets', side_effect=cluster.ClusterError('reconciliation-timeout')):
            with self.assertRaisesRegex(cluster.ClusterError, 'previous-token-restored'):
                cluster.sync_token(object(), 'new')
            self.assertEqual([call.args[1] for call in replace.call_args_list], ['new', 'old'])


if __name__ == '__main__':
    unittest.main()

class AmbiguousPatchTests(unittest.TestCase):
    def test_timed_out_initial_patch_attempts_restore(self):
        cluster = module('cluster_secrets')
        with patch.object(cluster, 'application_access', return_value={}), patch.object(cluster, 'read_token', return_value='old'), patch.object(cluster, 'replace_token', side_effect=[cluster.ClusterError('eso-token-update-failed'), None]) as replace:
            with self.assertRaisesRegex(cluster.ClusterError, 'previous-token-restored'):
                cluster.sync_token(object(), 'new')
            self.assertEqual([call.args[1] for call in replace.call_args_list], ['new', 'old'])

class TokenDiagnostics(unittest.TestCase):
    def test_rejected_token_reports_safe_preflight_stage(self):
        import io
        cluster = module('cluster_secrets')
        from bootstrap import PreflightError
        output = io.StringIO()
        with patch.object(cluster.config, 'load_kube_config'), patch.object(cluster.client, 'CustomObjectsApi', return_value=object()), patch.object(cluster, 'application_access', side_effect=PreflightError('eso-project-access-failed')), patch.dict('os.environ', {'ESO_BWS_ACCESS_TOKEN': 'synthetic'}), patch.object(cluster.sys, 'argv', ['cluster_secrets.py', 'sync-token']), patch.object(cluster.sys, 'stderr', output):
            self.assertEqual(cluster.main(), 1)
        self.assertIn('replacement-token-rejected:eso-project-access-failed', output.getvalue())
