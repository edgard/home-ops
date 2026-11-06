"""Only an exact successful uploader claim can become prunable under the Lease."""

import json

import pytest


def test_claim_requires_exact_job_uid_and_verified_receipt(adapters, tmp_path):
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploaded").mkdir()
    claim = {
        "operation": "op",
        "manifest_sha256": "a" * 64,
        "upload_job": {"uid": "job-uid"},
    }
    path = tmp_path / "uploads/op.json"
    path.write_text(json.dumps(claim))
    receipt = tmp_path / "uploaded/op.json"
    with pytest.raises(ValueError):
        adapters["capture"].release_upload_claim(tmp_path, "op", "job-uid")
    receipt.write_text(
        json.dumps(
            {
                "operation": "op",
                "manifest_sha256": "a" * 64,
                "snapshot": "b" * 64,
                "status": "ok",
            }
        )
    )
    with pytest.raises(ValueError):
        adapters["capture"].release_upload_claim(tmp_path, "op", "different-job")
    assert path.exists()
    adapters["capture"].release_upload_claim(tmp_path, "op", "job-uid")
    assert not path.exists()
    assert receipt.exists()
