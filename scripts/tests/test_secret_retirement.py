import subprocess
import unittest
import yaml
from test_secrets import ROOT


class SecretRetirementContracts(unittest.TestCase):
    def test_legacy_vault_maintenance_is_retired(self):
        self.assertFalse((ROOT / 'ansible/roles/talos/files/secrets.vault.yml').exists())
        self.assertFalse((ROOT / 'scripts/verify_migration.py').exists())
        tasks = yaml.safe_load((ROOT / 'Taskfile.yaml').read_text())['tasks']
        self.assertNotIn('secrets:verify-migration', tasks)
        for path in ROOT.glob('ansible/roles/*/tasks/*.yml'):
            self.assertNotIn('ansible-vault', path.read_text())
            self.assertNotIn('--vault-password-file', path.read_text())

    def test_credential_backups_remain_ignored(self):
        paths = ['.envrc.backup', '.vault-password.backup', 'ansible/roles/talos/files/secrets.yaml.backup', 'terraform/crash.123.log', 'terraform/terraform.tfstate.backup', 'terraform/recovery.tfplan.backup']
        result = subprocess.run(['git', 'check-ignore', '--', *paths], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(set(result.stdout.splitlines()), set(paths))


if __name__ == '__main__':
    unittest.main()
