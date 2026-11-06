"""Partial captures and retries retain an honest recovery ordering."""

from datetime import datetime

import pytest

from .test_safety import generation
from .test_upload_acceptance import repository as repository
from .test_upload_acceptance import snapshots


def test_latest_requires_every_selected_consumer_tag(adapters):
    rows = [
        {
            "id": "a" * 64,
            "tags": ["appdata", "appdata-consumer-demo", "appdata-consumer-other"],
            "paths": ["/data/appdata"],
            "hostname": "homelab",
            "time": "2026-11-01T00:00:00Z",
        },
        {
            "id": "b" * 64,
            "tags": ["appdata", "appdata-consumer-other"],
            "paths": ["/data/appdata"],
            "hostname": "homelab",
            "time": "2026-11-02T00:00:00Z",
        },
    ]
    choose = adapters["recovery"].choose_snapshot
    assert choose(rows, "latest", "/data/appdata", apps=["demo"]) == "a" * 64
    assert choose(rows, "latest", "/data/appdata", apps=["demo", "other"]) == "a" * 64
    with pytest.raises(ValueError, match="complete"):
        choose(rows, "latest", "/data/appdata", apps=["missing"])


def test_retried_upload_uses_capture_time_and_scope(repository, tmp_path, adapters):
    import hashlib
    import json

    root, manifest, _ = generation(tmp_path, adapters["data_tools"])
    manifest["captured_at"] = "2026-10-01T01:02:03.123456+02:00"
    raw = json.dumps(manifest).encode()
    (root / ".home-ops/manifest.json").write_bytes(raw)
    adapters["upload"].upload(
        "op", manifest, root=str(root), manifest_sha256=hashlib.sha256(raw).hexdigest()
    )
    [snapshot] = snapshots("appdata")
    assert datetime.fromisoformat(snapshot["time"]) == datetime.fromisoformat(
        manifest["captured_at"]
    )
    assert "appdata-consumer-demo" in snapshot["tags"]


def test_receipt_is_external_and_records_original_capture(adapters, tmp_path):
    import json

    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    receipt = tmp_path / "uploaded/op.json"
    adapters["upload"].write_receipt(receipt, manifest, sha, "a" * 64)
    data = json.loads(receipt.read_text())
    assert data == {
        "status": "ok",
        "operation": "op",
        "manifest_sha256": sha,
        "snapshot": "a" * 64,
        "captured_at": manifest["captured_at"],
    }
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert not (root / ".home-ops/uploaded.json").exists()
