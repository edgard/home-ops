"""Capture immutable file generations; invoked by the shared-data Ansible role."""

import argparse
import json
import math
import os
import shutil
import subprocess
import time
from pathlib import Path

import yaml
from data_tools import select_consumers, verify_manifest


def pvc_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if (
        path.is_symlink()
        or not path.is_dir()
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("application PVC is missing or redirects outside the root")
    return path


def required_bytes(root, pvcs):
    total = 0
    for relative in pvcs:
        for path in pvc_path(root, relative).rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
    return math.ceil(total * 2.4)


def copy_files(root, destination, pvcs, deadline=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for relative in pvcs:
        source = pvc_path(root, relative)
        target = destination / relative
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        timeout = max(1, deadline - time.time()) if deadline else 3600
        subprocess.run(
            [
                "rsync",
                "--archive",
                "--numeric-ids",
                "--fsync",
                "--delete",
                "--exclude=/.home-ops/",
                str(source) + "/",
                str(target) + "/",
            ],
            check=True,
            capture_output=True,
            timeout=timeout,
        )


def publish(source, target, *, registry=None, apps=None):
    source, target = Path(source), Path(target)
    manifest = source / ".home-ops/manifest.json"
    if not manifest.is_file() or target.exists():
        raise ValueError(
            "generation requires a manifest and a new immutable destination"
        )
    metadata = json.loads(manifest.read_text())
    verify_manifest(source, metadata, registry=registry, apps=apps)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in (source / ".home-ops").rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    for relative in metadata["files"]:
        with (source / relative).open("rb") as stream:
            os.fsync(stream.fileno())
    source.rename(target)
    descriptor = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prune_generations(root):
    root = Path(root)
    if not root.exists():
        return
    # Keep the newest successful generation and every upload still pending.
    completed = sorted(
        [
            path
            for path in root.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and (path / ".home-ops/uploaded.json").is_file()
        ],
        key=lambda path: path.stat().st_mtime,
    )
    for path in completed[:-1]:
        shutil.rmtree(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preseed", "final", "publish", "cleanup"])
    parser.add_argument("--registry", required=True)
    parser.add_argument("--apps", required=True)
    parser.add_argument("--root", default="/data/appdata")
    parser.add_argument("--staging", default="/staging")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--deadline", type=float)
    args = parser.parse_args()
    if not args.operation or not all(c.isalnum() or c == "-" for c in args.operation):
        parser.error("invalid operation identity")
    registry = yaml.safe_load(Path(args.registry).read_text())
    consumers = select_consumers(registry, args.apps.split(","))
    pvcs = [pvc for app in consumers.values() for pvc in app["pvcs"]]
    stage = Path(args.staging)
    progress = stage / "in-progress" / args.operation
    target = stage / "generations" / args.operation
    if args.action == "preseed":
        stage.mkdir(parents=True, exist_ok=True, mode=0o700)
        prune_generations(stage / "generations")
        if progress.exists() or target.exists():
            raise ValueError("operation staging already exists")
        if shutil.disk_usage(stage).free < required_bytes(args.root, pvcs):
            raise ValueError(
                "insufficient staging space for two generations plus twenty percent"
            )
        copy_files(args.root, progress, pvcs)
    elif args.action == "final":
        if not progress.is_dir():
            raise ValueError("online preseed required")
        copy_files(args.root, progress, pvcs, args.deadline)
    elif args.action == "publish":
        publish(progress, target, registry=registry, apps=args.apps.split(","))
    else:
        prune_generations(stage / "generations")
    print(
        json.dumps(
            {"status": "ok", "operation": args.operation, "generation": str(target)}
        )
    )


if __name__ == "__main__":
    main()
