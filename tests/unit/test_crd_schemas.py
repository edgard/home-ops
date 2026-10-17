import copy
import json

import pytest
import yaml
from jsonschema import Draft4Validator


@pytest.fixture
def schemas():
    from tests.support import schemas

    return schemas


@pytest.fixture
def crd():
    return {
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "fixtures.example.org"},
        "spec": {
            "group": "example.org",
            "names": {"kind": "Fixture"},
            "versions": [
                {
                    "name": "v1",
                    "served": True,
                    "schema": {
                        "openAPIV3Schema": {
                            "type": "object",
                            "properties": {
                                "spec": {
                                    "type": "object",
                                    "properties": {
                                        "properties": {
                                            "type": "object",
                                            "properties": {
                                                "enabled": {"type": "boolean"}
                                            },
                                        },
                                        "free": {
                                            "type": "object",
                                            "x-kubernetes-preserve-unknown-fields": True,
                                        },
                                    },
                                }
                            },
                        }
                    },
                }
            ],
        },
    }


def export(schemas, tmp_path, documents):
    source = tmp_path / "source.yaml"
    source.write_text(yaml.safe_dump_all(documents))
    schemas.export(tmp_path / "schemas", [source])
    return json.loads((tmp_path / "schemas/example.org/fixture_v1.json").read_text())


def test_strict_fields_and_schema_keyword_property(schemas, crd, tmp_path):
    schema = export(schemas, tmp_path, [crd])
    Draft4Validator.check_schema(schema)
    validator = Draft4Validator(schema)
    assert validator.is_valid(
        {"spec": {"properties": {"enabled": True}, "free": {"anything": "allowed"}}}
    )
    assert not validator.is_valid({"spec": {"properties": {"enabled": "wrong type"}}})
    assert not validator.is_valid({"spec": {"unexpected": True}})


def test_constraint_branches_preserve_parent_fields(schemas):
    schema = {
        "type": "object",
        "properties": {"type": {"type": "string"}, "value": {"type": "string"}},
        "oneOf": [
            {"properties": {"type": {"enum": ["IPAddress"]}}},
            {"properties": {"type": {"not": {"enum": ["IPAddress"]}}}},
        ],
    }
    validator = Draft4Validator(schemas.strict_schema(schema))
    assert validator.is_valid({"type": "Hostname", "value": "example.org"})
    assert not validator.is_valid({"type": "Hostname", "unexpected": "example.org"})


def test_nullable_int_or_string_and_preserved_fields(schemas):
    schema = {
        "type": "object",
        "properties": {
            "nullable": {
                "type": "object",
                "nullable": True,
                "properties": {"name": {"type": "string"}},
            },
            "port": {"x-kubernetes-int-or-string": True},
        },
    }
    validator = Draft4Validator(schemas.strict_schema(schema))
    assert validator.is_valid({"nullable": None, "port": "http"})
    assert validator.is_valid({"port": 8080})
    assert not validator.is_valid({"port": False})
    assert not validator.is_valid({"nullable": {"unexpected": True}})


@pytest.mark.parametrize(
    "schema",
    [
        None,
        {},
        {"type": "object", "properties": {"broken": False}},
        {"type": "nonsense"},
    ],
)
def test_missing_or_malformed_served_schema(schemas, crd, tmp_path, schema):
    if schema is None:
        crd["spec"]["versions"][0].pop("schema")
    else:
        crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"] = schema
    with pytest.raises(schemas.SchemaError):
        export(schemas, tmp_path, [crd])


def test_identical_duplicates_allowed_conflicts_rejected(schemas, crd, tmp_path):
    export(schemas, tmp_path, [crd, crd])
    other = copy.deepcopy(crd)
    other["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"][
        "different"
    ] = {"type": "string"}
    with pytest.raises(schemas.SchemaError):
        export(schemas, tmp_path, [crd, other])


def test_chart_label_selector_default(schemas, crd, tmp_path):
    crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"][
        "operator"
    ] = {
        "type": "string",
        "default": "=",
    }
    source = tmp_path / "selector.yaml"
    source.write_text(yaml.safe_dump(crd).replace("default: '='", "default: ="))
    schemas.export(tmp_path / "schemas", [source])
    assert (
        json.loads((tmp_path / "schemas/example.org/fixture_v1.json").read_text())[
            "properties"
        ]["operator"]["default"]
        == "="
    )
