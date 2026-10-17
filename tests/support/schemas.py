"""Export strict kubeconform schemas from repository and pinned chart CRDs."""

import copy
import json
import os
import re
from pathlib import Path

import yaml
from jsonschema import Draft4Validator
from jsonschema.exceptions import SchemaError as InvalidSchema

from tests.support.sources import KubernetesLoader


class SchemaError(ValueError):
    pass


def strict_schema(schema):
    """Traverse schema keywords, never a properties map as if it were a schema."""
    result = copy.deepcopy(schema)
    if not isinstance(result, dict):
        return result
    for keyword in ("properties", "patternProperties", "definitions"):
        if keyword in result:
            result[keyword] = {
                name: strict_schema(value) for name, value in result[keyword].items()
            }
    for keyword in ("additionalProperties", "additionalItems", "not", "items"):
        if isinstance(result.get(keyword), dict):
            result[keyword] = strict_schema(result[keyword])
        elif isinstance(result.get(keyword), list):
            result[keyword] = [strict_schema(value) for value in result[keyword]]
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in result:
            result[keyword] = [strict_schema(value) for value in result[keyword]]
    if (
        result.get("type") == "object"
        and ("properties" in result or "patternProperties" in result)
        and not result.get("x-kubernetes-preserve-unknown-fields")
    ):
        result.setdefault("additionalProperties", False)
    if result.get("x-kubernetes-int-or-string"):
        result.setdefault("type", ["integer", "string"])
    if result.get("nullable") and "type" in result:
        types = result["type"] if isinstance(result["type"], list) else [result["type"]]
        result["type"] = list(dict.fromkeys(types + ["null"]))
    return result


def export(destination, paths):
    schemas = {}
    label = "source"
    try:
        for path in paths:
            label = Path(path).name
            for document in yaml.load_all(
                Path(path).read_text(), Loader=KubernetesLoader
            ):
                if (
                    not isinstance(document, dict)
                    or document.get("kind") != "CustomResourceDefinition"
                ):
                    continue
                label = str(document.get("metadata", {}).get("name", "unnamed-crd"))
                spec = document["spec"]
                group, kind = spec["group"], spec["names"]["kind"].lower()
                for version in spec["versions"]:
                    if version["served"] is not True:
                        continue
                    name = version["name"]
                    if not all(
                        re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*", component)
                        for component in (group, kind, name)
                    ):
                        raise SchemaError("invalid-schema-path")
                    label = f"{group}/{kind}/{name}"
                    schema = version["schema"]["openAPIV3Schema"]
                    if not isinstance(schema, dict) or schema.get("type") != "object":
                        raise SchemaError("invalid-served-schema")
                    Draft4Validator.check_schema(schema)
                    strict = strict_schema(schema)
                    Draft4Validator.check_schema(strict)
                    key = (group, kind, name)
                    if key in schemas and schemas[key] != strict:
                        raise SchemaError("conflicting-served-schemas")
                    schemas[key] = strict
    except SchemaError as error:
        raise SchemaError(f"{error}:{label}") from None
    except InvalidSchema as error:
        location = "/".join(str(part) for part in error.absolute_path)
        raise SchemaError(f"invalid-served-schema:{label}:{location}") from None
    except (KeyError, TypeError, ValueError, OSError, yaml.YAMLError) as error:
        raise SchemaError(
            f"invalid-served-schema:{label}:{type(error).__name__}"
        ) from None
    for (group, kind, name), schema in schemas.items():
        directory = Path(destination) / group
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / f"{kind}_{name}.json"
        target.write_text(json.dumps(schema))
        os.chmod(target, 0o600)
    return len(schemas)
