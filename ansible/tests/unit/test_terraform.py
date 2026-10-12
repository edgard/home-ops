import unittest
from test_secrets import ROOT


class TerraformContracts(unittest.TestCase):
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
