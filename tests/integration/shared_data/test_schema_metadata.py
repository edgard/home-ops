"""Recovery cannot silently accept a generation without schema identities."""

import json

import pytest

from .test_safety import generation


def test_postgres_generation_requires_explicit_schema_versions(adapters, tmp_path):
    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    manifest["consumers"]["demo"].pop("schema_versions", None)
    with pytest.raises(ValueError, match="schema"):
        adapters["data_tools"].verify_manifest(root, manifest)


def test_schema_metadata_is_bound_to_checksummed_capture(adapters, tmp_path):
    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    metadata = {
        "server_version_num": 180003,
        "dump_version": "pg_dump (PostgreSQL) 18.3",
        "schema_sha256": "a" * 64,
    }
    manifest["consumers"]["demo"]["schema_versions"] = {"demo": metadata}
    sidecar = root / "selfhosted/demo/.home-ops/databases/demo.schema.json"
    sidecar.write_text(json.dumps({**metadata, "schema_sha256": "b" * 64}))
    manifest["files"][str(sidecar.relative_to(root))] = adapters["data_tools"].digest(
        sidecar
    )
    with pytest.raises(ValueError, match="schema"):
        adapters["data_tools"].verify_manifest(root, manifest)
