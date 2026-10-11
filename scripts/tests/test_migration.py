import subprocess
import unittest
from unittest.mock import patch
from test_secrets import module


class MigrationTests(unittest.TestCase):
    def test_retire_only_known_data_addresses(self):
        migration = module('migrate_state')
        state = {'resources': [{'mode': 'data', 'type': 'bitwarden-secrets_secret', 'name': 'cloudflare_token'}, {'mode': 'managed', 'type': 'cloudflare_dns_record', 'name': 'example'}]}
        self.assertEqual(migration.retired_addresses(state), ['data.bitwarden-secrets_secret.cloudflare_token'])
        state['resources'].append({'mode':'data','type':'bitwarden-secrets_secret','name':'unexpected'})
        with self.assertRaisesRegex(migration.MigrationError, '^unexpected-bitwarden-state-address$'):
            migration.retired_addresses(state)

    def test_managed_resource_cannot_be_removed(self):
        migration = module('migrate_state')
        state = {'resources': [{'mode': 'managed', 'type': 'bitwarden-secrets_secret', 'name': 'cloudflare_token'}]}
        with self.assertRaisesRegex(migration.MigrationError, '^unexpected-bitwarden-state-address$'):
            migration.retired_addresses(state)

    def test_round_trip_comparison_never_displays_values(self):
        migration = module('verify_migration')
        with patch.dict('os.environ', {'TALOS_SECRETS_YAML': 'new PRIVATE'}):
            with self.assertRaisesRegex(migration.VerificationError, '^migration-round-trip-mismatch:TALOS_SECRETS_YAML$'):
                migration.compare({'TALOS_SECRETS_YAML': 'old PRIVATE'})
