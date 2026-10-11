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

class InfrastructureOwnershipTests(unittest.TestCase):
    def test_tailscale_shared_secret_uses_existing_eso_item_name(self):
        import tomllib
        import yaml
        from test_secrets import ROOT
        manifest = tomllib.loads((ROOT / 'secretspec.toml').read_text())
        eso = yaml.safe_load((ROOT / 'apps/platform-system/tailscale-router/manifests/tailscale-router-credentials.externalsecret.yaml').read_text())
        shared_key = eso['spec']['data'][0]['remoteRef']['key']
        declaration = manifest['profiles']['default']['TF_VAR_tailscale_client_secret']
        self.assertEqual(declaration['ref']['item'], shared_key)
        self.assertEqual(declaration['providers'], ['applications'])

    def test_operator_exclusive_infrastructure_values_use_operator_project(self):
        import tomllib
        from test_secrets import ROOT
        profile = tomllib.loads((ROOT / 'secretspec.toml').read_text())['profiles']['default']
        self.assertEqual(profile['TF_VAR_cloudflare_zone_id']['providers'], ['operator'])
        self.assertEqual(profile['TF_VAR_tailscale_client_id']['providers'], ['operator'])
        self.assertEqual(profile['TF_VAR_tailscale_client_id']['ref']['item'], 'tailscale_oauth_client_id')
