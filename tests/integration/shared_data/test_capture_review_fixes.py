"""Review regressions: content-correct copies and durable directory publication."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml

from tests.support.data_generation import schema_metadata
from tests.support.runtime import ROOT

from .test_safety import generation, registry


@pytest.fixture
def linux_files(operations_image):
    directory = ROOT / ".pytest_cache" / ("native-review-" + uuid.uuid4().hex[:10])
    directory.mkdir(mode=0o700, parents=True)
    files = ROOT / "ansible/roles/shared_data/files"
    (directory / "registry.yaml").write_text(yaml.safe_dump(registry()))

    def run(script, *args):
        return subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "python",
                "-v",
                f"{files}:/drafts:ro",
                "-v",
                f"{directory}:/work",
                operations_image,
                "/drafts/" + script,
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )

    try:
        yield directory, run
    finally:
        shutil.rmtree(directory)


def test_native_final_detects_same_size_preserved_mtime_after_preseed(linux_files):
    directory, run = linux_files
    source = directory / "appdata/selfhosted/demo/file"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original")
    arguments = [
        "--registry",
        "/work/registry.yaml",
        "--apps",
        "demo",
        "--root",
        "/work/appdata",
        "--staging",
        "/work/staging",
        "--operation",
        "op",
    ]
    run("capture.py", "preseed", *arguments, "--database-bytes", "100")
    staged = directory / "staging/in-progress/op/selfhosted/demo/file"
    assert staged.read_bytes() == b"original"
    before = source.stat()
    source.write_bytes(b"modified")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    run("capture.py", "final", *arguments, "--deadline", str(time.time() + 30))
    assert staged.read_bytes() == b"modified"


def test_native_recovery_detects_same_size_preserved_mtime_destination(
    linux_files, adapters
):
    directory, run = linux_files
    operation = directory / "staging/restores/recover"
    staged = operation / "data/appdata"
    dump = staged / "selfhosted/demo/.home-ops/databases/demo.dump"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"synthetic-dump")
    schema_metadata(dump)
    source = staged / "selfhosted/demo/file"
    source.write_bytes(b"original")
    manifest = adapters["data_tools"].make_manifest(
        staged, registry(), ["demo"], "capture", {"demo": ["image:1"]}
    )
    raw = json.dumps(manifest).encode()
    (staged / ".home-ops").mkdir()
    (staged / ".home-ops/manifest.json").write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    (operation / "recovery.json").write_text(
        json.dumps(
            {
                "operation": "recover",
                "snapshot": "a" * 64,
                "manifest_sha256": sha,
                "root": "/work/staging/restores/recover/data/appdata",
                "apps": ["demo"],
            }
        )
    )
    live = directory / "live/selfhosted/demo/file"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"diverged")
    os.utime(live, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
    run(
        "recovery.py",
        "files",
        "--registry",
        "/work/registry.yaml",
        "--apps",
        "demo",
        "--operation",
        "recover",
        "--staging",
        "/work/staging",
        "--live-root",
        "/work/live",
        "--images",
        json.dumps({"demo": ["image:1"]}),
        "--manifest-sha256",
        sha,
        "--confirm",
    )
    assert live.read_bytes() == b"original"


def test_final_copy_verifies_destination_after_successful_rsync(
    adapters, tmp_path, monkeypatch
):
    source = tmp_path / "source/selfhosted/demo"
    source.mkdir(parents=True)
    (source / "file").write_bytes(b"current")
    target = tmp_path / "target/selfhosted/demo"
    target.mkdir(parents=True)
    (target / "file").write_bytes(b"wrong!!")
    monkeypatch.setattr(
        adapters["capture"].subprocess, "run", lambda *args, **kwargs: None
    )
    with pytest.raises(ValueError, match="destination|copy"):
        adapters["capture"].copy_files(
            tmp_path / "source",
            tmp_path / "target",
            ["selfhosted/demo"],
            time.time() + 30,
            checksum=True,
        )


def publication_events(capture, source, monkeypatch, fail=None):
    events = []
    inodes = {
        path.stat().st_ino: path
        for path in [source, *source.rglob("*")]
        if not path.is_symlink()
    }
    opened = {}
    real_open, real_fsync, real_rename = os.open, os.fsync, Path.rename

    def opened_path(path, *args, **kwargs):
        fd = real_open(path, *args, **kwargs)
        opened[fd] = Path(path)
        return fd

    def fsync(fd):
        details = os.fstat(fd)
        kind = "dir" if stat.S_ISDIR(details.st_mode) else "file"
        path = opened[fd] if kind == "dir" else inodes[details.st_ino]
        events.append((kind, path))
        if fail and fail(kind, path, events):
            raise OSError("injected fsync failure")
        real_fsync(fd)

    def rename(path, target):
        events.append(("rename", path))
        return real_rename(path, target)

    monkeypatch.setattr(capture.os, "open", opened_path)
    monkeypatch.setattr(capture.os, "fsync", fsync)
    monkeypatch.setattr(Path, "rename", rename)
    return events


def test_publication_flushes_files_then_bottom_up_dirs_and_both_parents(
    adapters, tmp_path, monkeypatch
):
    source, _, sha = generation(tmp_path / "in-progress", adapters["data_tools"])
    target = tmp_path / "new/nested/generations/op"
    events = publication_events(adapters["capture"], source, monkeypatch)
    assert (
        adapters["capture"].publish(source, target, registry=registry(), apps=["demo"])
        == sha
    )
    rename = next(index for index, event in enumerate(events) if event[0] == "rename")
    file_indices = [index for index, event in enumerate(events) if event[0] == "file"]
    directory_indices = {
        path: index
        for index, (kind, path) in enumerate(events[:rename])
        if kind == "dir"
    }
    # Generation inode paths are recorded under their pre-rename names.
    expected = [
        source,
        *[
            source / path.relative_to(target)
            for path in target.rglob("*")
            if path.is_dir()
        ],
    ]
    assert all(path in directory_indices for path in expected)
    assert max(file_indices) < min(directory_indices.values()) < rename
    for path in expected:
        if path != source:
            assert directory_indices[path] < directory_indices[path.parent]
    assert (
        directory_indices[target.parent]
        < directory_indices[target.parent.parent]
        < directory_indices[tmp_path / "new"]
        < directory_indices[tmp_path]
    )
    assert set(events[rename + 1 :]) >= {("dir", source.parent), ("dir", target.parent)}


def test_directory_flush_failure_prevents_publication(adapters, tmp_path, monkeypatch):
    source, _, _ = generation(tmp_path / "in-progress", adapters["data_tools"])
    target = tmp_path / "generations/op"
    events = publication_events(
        adapters["capture"],
        source,
        monkeypatch,
        lambda kind, path, events: kind == "dir" and path == source,
    )
    with pytest.raises(OSError, match="injected"):
        adapters["capture"].publish(source, target, registry=registry(), apps=["demo"])
    assert source.exists() and not target.exists()
    assert not any(kind == "rename" for kind, path in events)


def test_parent_flush_failure_after_rename_does_not_acknowledge_success(
    adapters, tmp_path, monkeypatch
):
    source, _, _ = generation(tmp_path / "in-progress", adapters["data_tools"])
    target = tmp_path / "generations/op"
    publication_events(
        adapters["capture"],
        source,
        monkeypatch,
        lambda kind, path, events: (
            kind == "dir"
            and path == source.parent
            and any(event[0] == "rename" for event in events)
        ),
    )
    with pytest.raises(OSError, match="injected"):
        adapters["capture"].publish(source, target, registry=registry(), apps=["demo"])
    assert target.exists() and not source.exists()
