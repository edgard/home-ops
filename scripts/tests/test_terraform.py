import unittest
from test_secrets import ROOT


class TerraformContracts(unittest.TestCase):
    def test_native_variables_replace_bitwarden_data_reads(self):
        main = (ROOT / 'terraform/main.tf').read_text()
        tailscale = (ROOT / 'terraform/tailscale.tf').read_text()
        self.assertNotIn('bitwarden-secrets', main + tailscale)
        self.assertIn('var.cloudflare_api_token', main)
        self.assertIn('var.cloudflare_zone_id', main)
        self.assertIn('var.tailscale_client_secret', tailscale)

    def test_to_fu_environment_has_scoped_variables(self):
        import yaml
        for action in ('plan', 'apply'):
            tasks = yaml.safe_load((ROOT / f'ansible/roles/tofu/tasks/{action}.yml').read_text())
            env = tasks[1]['environment']
            self.assertIn('TF_VAR_cloudflare_api_token', env)
            self.assertNotIn('BWS_ACCESS_TOKEN', env)
            self.assertNotIn('BW_ACCESS_TOKEN', env)
            self.assertTrue(tasks[1]['no_log'])
