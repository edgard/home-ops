import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[3]


class ChartSchemaContracts(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('export_schemas', ROOT / 'ansible/roles/kubernetes_validation/files/export_schemas.py')
        self.schemas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.schemas)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.crd = {'kind': 'CustomResourceDefinition', 'metadata': {'name': 'fixtures.example.org'}, 'spec': {'group': 'example.org', 'names': {'kind': 'Fixture'}, 'versions': [{'name': 'v1', 'served': True, 'schema': {'openAPIV3Schema': {'type': 'object', 'properties': {'spec': {'type': 'object', 'properties': {'properties': {'type': 'object', 'properties': {'enabled': {'type': 'boolean'}}}, 'free': {'type': 'object', 'x-kubernetes-preserve-unknown-fields': True}}}}}}}]}}

    def export(self, documents):
        source = self.root / 'source.yaml'
        source.write_text(yaml.safe_dump_all(documents))
        self.schemas.export(self.root / 'schemas', [source])
        return json.loads((self.root / 'schemas/example.org/fixture_v1.json').read_text())

    def test_strict_schema_checks_types_unknown_fields_and_property_named_properties(self):
        from jsonschema import Draft4Validator
        schema = self.export([self.crd])
        Draft4Validator.check_schema(schema)
        validator = Draft4Validator(schema)
        self.assertTrue(validator.is_valid({'spec': {'properties': {'enabled': True}, 'free': {'anything': 'allowed'}}}))
        self.assertFalse(validator.is_valid({'spec': {'properties': {'enabled': 'wrong type'}}}))
        self.assertFalse(validator.is_valid({'spec': {'unexpected': True}}))

    def test_constraint_branches_preserve_parent_properties(self):
        from jsonschema import Draft4Validator
        schema = {'type': 'object', 'properties': {'type': {'type': 'string'}, 'value': {'type': 'string'}}, 'oneOf': [{'properties': {'type': {'enum': ['IPAddress']}}}, {'properties': {'type': {'not': {'enum': ['IPAddress']}}}}]}
        strict = self.schemas.strict_schema(schema)
        self.assertTrue(Draft4Validator(strict).is_valid({'type': 'Hostname', 'value': 'example.org'}))
        self.assertFalse(Draft4Validator(strict).is_valid({'type': 'Hostname', 'unexpected': 'example.org'}))

    def test_kubernetes_nullable_and_int_or_string_semantics(self):
        from jsonschema import Draft4Validator
        schema = {'type': 'object', 'properties': {'nullable': {'type': 'object', 'nullable': True, 'properties': {'name': {'type': 'string'}}}, 'port': {'x-kubernetes-int-or-string': True}}}
        validator = Draft4Validator(self.schemas.strict_schema(schema))
        self.assertTrue(validator.is_valid({'nullable': None, 'port': 'http'}))
        self.assertTrue(validator.is_valid({'port': 8080}))
        self.assertFalse(validator.is_valid({'port': False}))
        self.assertFalse(validator.is_valid({'nullable': {'unexpected': True}}))

    def test_missing_or_malformed_served_schema_fails(self):
        for schema in ({}, {'type': 'object', 'properties': {'broken': False}}, {'type': 'nonsense'}):
            self.crd['spec']['versions'][0]['schema']['openAPIV3Schema'] = schema
            with self.assertRaises(self.schemas.SchemaError):
                self.export([self.crd])
        self.crd['spec']['versions'][0].pop('schema')
        with self.assertRaises(self.schemas.SchemaError):
            self.export([self.crd])

    def test_conflicting_definitions_fail_identical_duplicates_work(self):
        self.export([self.crd, self.crd])
        other = json.loads(json.dumps(self.crd))
        other['spec']['versions'][0]['schema']['openAPIV3Schema']['properties']['different'] = {'type': 'string'}
        with self.assertRaises(self.schemas.SchemaError):
            self.export([self.crd, other])

    def test_chart_label_selector_default_equals_is_a_safe_scalar(self):
        schema = self.crd['spec']['versions'][0]['schema']['openAPIV3Schema']
        schema['properties']['operator'] = {'type': 'string', 'default': '='}
        source = self.root / 'selector.yaml'
        source.write_text(yaml.safe_dump(self.crd).replace("default: '='", 'default: ='))
        self.schemas.export(self.root / 'schemas', [source])
        exported = json.loads((self.root / 'schemas/example.org/fixture_v1.json').read_text())
        self.assertEqual(exported['properties']['operator']['default'], '=')

    def test_route_parser_uses_safe_kubernetes_yaml_dialect(self):
        tasks = (ROOT / 'ansible/roles/kubernetes_validation/tasks/check-uptime.yml').read_text()
        self.assertIn('from_kubernetes_yaml_all', tasks)
        from kubernetes_yaml import from_kubernetes_yaml_all
        documents = from_kubernetes_yaml_all('kind: HTTPRoute\n---\ndefault: =\n')
        self.assertEqual(documents[0]['kind'], 'HTTPRoute')
        self.assertEqual(documents[1]['default'], '=')
        with self.assertRaises(Exception):
            from_kubernetes_yaml_all('!!python/object/apply:os.system ["false"]')

    def test_rendering_precedes_schema_gate_and_includes_chart_crds(self):
        tasks = yaml.safe_load((ROOT / 'ansible/roles/kubernetes_validation/tasks/main.yml').read_text())
        block = next(task['block'] for task in tasks if 'block' in task)
        names = [task['name'] for task in block]
        self.assertLess(names.index('Render all declared Helm applications'), names.index('Validate raw manifest schemas'))
        render = (ROOT / 'ansible/roles/kubernetes_validation/tasks/render-app.yml').read_text()
        self.assertIn('--include-crds', render)
        self.assertNotIn('-ignore-missing-schemas', str(block))


if __name__ == '__main__':
    unittest.main()
