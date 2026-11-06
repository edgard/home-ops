"""Synthetic metadata for intentionally fake PostgreSQL archives in contract tests."""

import json
import os
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
    import yaml

    from tests.support.runtime import ROOT

    image = yaml.safe_load(
        (ROOT / "apps/selfhosted/shared-data/values.yaml").read_text()
    )["controllers"]["main"]["containers"]["operations"]["image"]
    pinned = image["repository"] + ":" + image["tag"] + "@" + image["digest"]
    return (
        os.environ.get("HOME_OPS_DATA_TOOLS_TEST_IMAGE", pinned) if native else pinned
    )


def fixture_actor():
    """Share private bind artifacts with the pytest coordinator's numeric identity.

    Dedicated numeric-ownership/capability cases retain their explicit root
    profile. General adapter fixtures must use one identity on both sides of
    the bind; Linux preserves ownership where macOS file sharing can mask it.
    """
    return [
        "--user",
        f"{os.geteuid()}:{os.getegid()}",
        "--env",
        "HOME=/tmp",
    ]
