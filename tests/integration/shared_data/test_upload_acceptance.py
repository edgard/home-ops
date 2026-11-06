import json
import subprocess

import pytest

from .test_safety import generation


@pytest.fixture
def repository(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "repository"))
    monkeypatch.setenv("RESTIC_PASSWORD", "synthetic-only")
    monkeypatch.setenv("RESTIC_CACHE_DIR", str(tmp_path / "cache"))
    subprocess.run(["restic", "init"], capture_output=True, check=True)


def snapshots(tag):
    return json.loads(
        subprocess.run(
            ["restic", "snapshots", "--json", "--tag", tag],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )


def test_real_remote_payload_verification_and_original_identity(
    repository, tmp_path, adapters
):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    # Other live applications and raw engines must not enter the selected generation.
    for relative in [
        "platform-system/postgresql/PG_VERSION",
        "platform-system/redis/appendonly.aof",
        "selfhosted/other/private",
        "selfhosted/shared-data-staging/secret",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not-selected")
    uploader = adapters["upload"]
    first = uploader.upload("op", manifest, root=str(root), manifest_sha256=sha)
    second = uploader.upload("op", manifest, root=str(root), manifest_sha256=sha)
    assert first != second
    assert {row["id"] for row in snapshots("appdata")} == {first, second}
    assert snapshots("appdata-pending") == []
    for row in [first, second]:
        listing = subprocess.run(
            ["restic", "ls", "--json", "--recursive", row],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "/other/private" not in listing
        assert "/postgresql/PG_VERSION" not in listing
        assert "/redis/appendonly.aof" not in listing
        assert "/shared-data-staging/secret" not in listing


def test_remote_hash_failure_never_promotes(repository, tmp_path, adapters):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    with pytest.raises(ValueError, match="checksum"):
        adapters["upload"].upload(
            "op",
            manifest,
            root=str(root),
            manifest_sha256=sha,
            hash_remote=lambda command: "a" * 64,
        )
    assert snapshots("appdata") == []
    assert len(snapshots("appdata-pending")) == 1


def test_real_restic_code3_stays_pending(repository, tmp_path, adapters):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    unreadable = root / "selfhosted/demo/unreadable"

    def run(command):
        if "backup" in command:
            unreadable.write_bytes(b"synthetic-unreadable")
            unreadable.chmod(0)
        return adapters["upload"].run_native(command)

    try:
        with pytest.raises(ValueError, match="incomplete"):
            adapters["upload"].upload(
                "op", manifest, run=run, root=str(root), manifest_sha256=sha
            )
        assert snapshots("appdata") == []
        assert len(snapshots("appdata-pending")) == 1
    finally:
        unreadable.chmod(0o600)


def test_wrong_journal_digest_starts_no_backup(repository, tmp_path, adapters):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    with pytest.raises(ValueError, match="manifest"):
        adapters["upload"].upload(
            "op", manifest, root=str(root), manifest_sha256="0" * 64
        )
    assert snapshots("appdata-pending") == []


def test_real_explicit_legacy_pvc_preserves_single_snapshot_file_semantics(
    repository, tmp_path, adapters
):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    for pvc in [
        "selfhosted/unchanged",
        "selfhosted/unlisted",
        "platform-system/postgresql",
    ]:
        (root / pvc).mkdir(parents=True, exist_ok=True)
        (root / pvc / "file").write_text(pvc)
    snapshot = adapters["upload"].upload(
        "op",
        manifest,
        root=str(root),
        manifest_sha256=sha,
        legacy_pvcs=["selfhosted/unchanged"],
    )
    stored = subprocess.run(
        ["restic", "dump", snapshot, str(root / "selfhosted/unchanged/file")],
        check=True,
        capture_output=True,
    ).stdout
    assert stored == b"selfhosted/unchanged"
    listing = subprocess.run(
        ["restic", "ls", "--json", "--recursive", snapshot],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "/selfhosted/unlisted/file" not in listing
    assert "/platform-system/postgresql/file" not in listing
    assert len(snapshots("appdata")) == 1


@pytest.mark.parametrize(
    "legacy",
    [
        "selfhosted/demo",
        "../private",
        "/selfhosted/unsafe",
        "platform-system/postgresql",
        "platform-system/redis",
        "selfhosted/shared-data-staging",
    ],
)
def test_legacy_allowlist_rejects_overlap_unsafe_and_infra_before_upload(
    repository, tmp_path, adapters, legacy
):
    root, manifest, sha = generation(tmp_path, adapters["data_tools"])
    with pytest.raises(ValueError):
        adapters["upload"].upload(
            "op", manifest, root=str(root), manifest_sha256=sha, legacy_pvcs=[legacy]
        )
    assert snapshots("appdata-pending") == []
