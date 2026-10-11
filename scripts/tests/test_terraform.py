import unittest
from test_secrets import ROOT


class TerraformContracts(unittest.TestCase):
    def test_cloudflare_pin_stays_within_renovate_compatibility_limit(self):
        import re
        blocks = re.findall(r'\{[^{}]*\}', (ROOT / '.renovaterc.json5').read_text())
        rules = [block for block in blocks if '"terraform-provider"' in block and '"cloudflare/cloudflare"' in block]
        self.assertEqual(len(rules), 1, 'Guard the provider query-parameter regression from automatic reintroduction')
        limit = re.search(r'allowedVersions:\s*"<([0-9.]+)"', rules[0]).group(1)
        version = re.search(r'cloudflare\s*=\s*\{[^}]*version\s*=\s*"([0-9.]+)"', (ROOT / 'terraform/main.tf').read_text()).group(1)
        self.assertLess(tuple(map(int, version.split('.'))), tuple(map(int, limit.split('.'))))

    def test_zone_input_stays_public_and_preserves_resource_state_sensitivity(self):
        import json
        from pathlib import Path
        import re
        import subprocess
        import tempfile
        variables = (ROOT / 'terraform/variables.tf').read_text()
        declaration = re.search(r'(?ms)^variable "cloudflare_zone_id"\s*\{.*?^\}', variables).group()
        assignment = re.search(r'(?m)^\s*zone_id\s*=\s*(.+)', (ROOT / 'terraform/main.tf').read_text()).group(1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'main.tf').write_text(declaration)
            (path / 'fixture.auto.tfvars').write_text('cloudflare_zone_id = "synthetic-zone"\n')
            result = subprocess.run(['tofu', 'console', '-no-color'], cwd=path, input=f'jsonencode([issensitive(var.cloudflare_zone_id), issensitive({assignment})])\n', capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(json.loads(result.stdout)), [False, True])

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
