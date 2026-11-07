"""Execute the deployed shell commands with owned client stand-ins."""

import os
import subprocess
import sys

import pytest

from tests.support.runtime import ROOT
from tests.support.sources import read_yaml


def controller(name, application="sure"):
    return read_yaml(ROOT / f"apps/selfhosted/{application}/values.yaml")[
        "controllers"
    ][name]["containers"]["app"]


def executable(path, body):
    path.write_text(body)
    path.chmod(0o700)


def test_redis_command_reaches_server_with_persistent_authenticated_config(tmp_path):
    binary = tmp_path / "redis-server"
    executable(binary, '#!/bin/sh\nprintf "%s" "$1" > "$CALL_RECORD"\n')
    config = tmp_path / "redis.conf"
    command = [
        x.replace("/tmp/redis.conf", str(config))
        for x in controller("redis")["command"]
    ]
    marker = tmp_path / "called"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "CALL_RECORD": str(marker),
        "REDIS_PASSWORD": "synthetic-only",
    }
    subprocess.run(command, env=env, check=True, timeout=10)
    assert marker.exists(), "the configured shell must actually exec Redis"
    assert marker.read_text() == str(config)
    assert "appendonly yes" in config.read_text()
    assert "requirepass synthetic-only" in config.read_text()


@pytest.mark.parametrize(
    "application,subdir", [("sure", ""), ("sparkyfitness", "postgresql")]
)
@pytest.mark.parametrize("failure", [False, True])
def test_backup_shell_publishes_only_success_and_keeps_seven(
    tmp_path, failure, application, subdir
):
    binary = tmp_path / "pg_dump"
    executable(
        binary,
        f'#!{sys.executable}\nimport os,sys\nfrom pathlib import Path\np=next(x.split("=",1)[1] for x in sys.argv if x.startswith("--file="))\nPath(p).write_bytes(b"synthetic archive")\nsys.exit(int(os.environ["DUMP_FAILURE"]))\n',
    )
    backup_root = tmp_path / "backups"
    backups = backup_root / subdir
    backups.mkdir(parents=True)
    for i in range(8):
        path = backups / f"old-{i}.dump"
        path.write_bytes(b"old")
        os.utime(path, (i + 1, i + 1))
    command = [
        x.replace("/backups", str(backup_root))
        for x in controller("backup", application)["command"]
    ]
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "DUMP_FAILURE": "1" if failure else "0",
    }
    result = subprocess.run(command, env=env, timeout=10)
    assert result.returncode == (1 if failure else 0)
    assert not list(backups.glob("*.tmp"))
    if failure:
        assert len(list(backups.glob("*.dump"))) == 8
    else:
        assert len(list(backups.glob("*.dump"))) == 7
        assert any(
            p.read_bytes() == b"synthetic archive" for p in backups.glob("*.dump")
        )
