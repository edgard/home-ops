"""The temporary recovery server receives only a verified RDB and hashed auth."""

import hashlib
import json
import subprocess
import uuid

from tests.support.runtime import ROOT


def test_native_source_preparation_checks_hash_and_permissions(operations_image):
    directory = ROOT / ".pytest_cache" / ("redis-source-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, mode=0o700)
    (directory / "source.rdb").write_bytes(b"REDIS0012synthetic-payload")
    (directory / "password").write_text("synthetic-password" * 3)
    (directory / "data").mkdir()
    files = ROOT / "ansible/roles/shared_data/files"
    volume = "home-ops-redis-source-" + uuid.uuid4().hex
    subprocess.run(
        ["docker", "volume", "create", "--label", "home-ops-test=redis-source", volume],
        capture_output=True,
        check=True,
    )
    try:
        base = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "DAC_READ_SEARCH",
            "-v",
            str(directory) + ":/work:ro",
            "-v",
            volume + ":/redis",
            "-v",
            str(files) + ":/adapters:ro",
            operations_image,
        ]
        argv = [
            "/adapters/redis_source.py",
            "--source",
            "/work/source.rdb",
            "--destination",
            "/redis",
            "--sha256",
            "0" * 64,
            "--password-file",
            "/work/password",
        ]
        bad = subprocess.run(base + argv, capture_output=True, text=True)
        assert bad.returncode != 0
        assert list((directory / "data").iterdir()) == []
        argv[argv.index("--sha256") + 1] = hashlib.sha256(
            (directory / "source.rdb").read_bytes()
        ).hexdigest()
        result = subprocess.run(base + argv, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        permissions = subprocess.run(
            base
            + [
                "-c",
                "import os,json; from pathlib import Path; print(json.dumps({p.name: [p.stat().st_uid,p.stat().st_gid,p.stat().st_mode & 4095] for p in Path('/redis').iterdir()}))",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(permissions.stdout) == {
            "dump.rdb": [999, 999, 0o600],
            "recovery.acl": [999, 999, 0o600],
        }
        acl = subprocess.run(
            base + ["-c", "print(open('/redis/recovery.acl').read())"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "synthetic-password" not in acl
        assert "+pexpiretime" in acl and "-@all" in acl
        assert (
            "#" + hashlib.sha256(("synthetic-password" * 3).encode()).hexdigest() in acl
        )
        duplicate = subprocess.run(base + argv, capture_output=True, text=True)
        assert duplicate.returncode != 0
    finally:
        subprocess.run(
            ["docker", "volume", "rm", volume], capture_output=True, check=True
        )
        import shutil

        shutil.rmtree(directory)
