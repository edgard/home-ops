"""Synthetic metadata for intentionally fake PostgreSQL archives in contract tests."""

import json
from pathlib import Path


def schema_metadata(dump):
    path = Path(dump).with_suffix(".schema.json")
    path.write_text(
        json.dumps(
            {
                "server_version_num": 180003,
                "dump_version": "pg_dump (PostgreSQL) 18.3",
                "schema_sha256": "a" * 64,
            }
        )
        + "\n"
    )


def operations_image(*, native=True):
    """Use the published clients in CI; permit an explicit same-Dockerfile native local build."""
    import os

    import yaml

    from tests.support.runtime import ROOT

    image = yaml.safe_load(
        (ROOT / "apps/selfhosted/shared-data/values.yaml").read_text()
    )["controllers"]["main"]["containers"]["operations"]["image"]
    pinned = image["repository"] + ":" + image["tag"] + "@" + image["digest"]
    return (
        os.environ.get("HOME_OPS_DATA_TOOLS_TEST_IMAGE", pinned) if native else pinned
    )
