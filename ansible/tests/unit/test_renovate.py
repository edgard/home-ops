import re
import unittest

import yaml

from test_secrets import ROOT


def renovate_config():
    # The repository uses YAML-compatible JSON5 with whole-line comments.
    source = (ROOT / '.renovaterc.json5').read_text()
    return yaml.safe_load(re.sub(r'(?m)^\s*//.*$', '', source))


def regex(pattern):
    return re.compile(re.sub(r'\(\?<([A-Za-z][A-Za-z0-9_]*)>', r'(?P<\1>', pattern))


class OperatorToolDiscovery(unittest.TestCase):
    def test_operator_pins_are_discovered_from_their_own_annotations(self):
        path = 'ansible/roles/operator_secrets/defaults/main.yml'
        source = (ROOT / path).read_text()
        defaults = yaml.safe_load(source)
        expected = {
            ('github-releases', 'cachix/secretspec', defaults['operator_secrets_secretspec_version']),
            ('github-releases', 'bitwarden/sdk-sm', defaults['operator_secrets_bws_version']),
        }
        dependencies = []
        for manager in renovate_config()['customManagers']:
            if manager['customType'] != 'regex':
                continue
            if not any(regex(pattern[1:-1]).search(path) for pattern in manager['managerFilePatterns']):
                continue
            for pattern in manager['matchStrings']:
                for match in regex(pattern).finditer(source):
                    fields = match.groupdict()
                    dependencies.append((fields.get('datasource', manager.get('datasourceTemplate')), fields.get('depName', manager.get('depNameTemplate')), fields.get('currentValue')))
        self.assertCountEqual(dependencies, expected, 'Both operator pins must be discovered exactly once with their current scalar versions')

    def test_sdk_release_filter_accepts_only_bws_versions(self):
        rules = [rule for rule in renovate_config()['packageRules'] if 'github-releases' in rule.get('matchDatasources', []) and 'bitwarden/sdk-sm' in rule.get('matchPackageNames', [])]
        self.assertEqual(len(rules), 1, 'The shared SDK repository needs a BWS-specific release filter')
        pattern = regex(rules[0]['extractVersion'])
        for tag, version in [('bws-v2.1.1', '2.1.1'), ('bws-v3.0.0-beta.1', '3.0.0-beta.1'), ('rust-v3.0.0', None), ('python-v3.0.0', None), ('dotnet-v3.0.0', None), ('v3.0.0', None)]:
            with self.subTest(tag=tag):
                match = pattern.search(tag)
                self.assertEqual(match.group('version') if match else None, version)
