"""Capture immutable file generations; invoked by the shared-data Ansible role."""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import yaml
from data_tools import (
    digest,
    remaining,
    select_consumers,
    uses_shared_redis,
    verify_manifest,
)


def pvc_path(root, relative):
    root = Path(root).resolve()
    path = root / relative
    if (
        path.is_symlink()
        or path.parent.is_symlink()
        or not path.is_dir()
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("application PVC is missing or redirects outside the root")
    return path


def required_bytes(root, pvcs, *, database_bytes=0, redis_bytes=0):
    total = 0
    for relative in pvcs:
        for path in pvc_path(root, relative).rglob("*"):
            remaining()
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
    if min(database_bytes, redis_bytes) < 0:
        raise ValueError("negative capture estimate")
    return math.ceil((total + database_bytes + redis_bytes) * 2.4)


def copy_inventory(root, deadline):
    inventory = {}
    for path in Path(root).rglob("*"):
        remaining(deadline)
        relative = path.relative_to(root)
        if relative.parts[0] == ".home-ops":
            continue
        if path.is_symlink():
            inventory[str(relative)] = ("symlink", os.readlink(path))
        elif path.is_file():
            inventory[str(relative)] = ("file", digest(path, deadline=deadline))
        elif path.is_dir():
            inventory[str(relative)] = ("directory", None)
        else:
            raise ValueError("unsupported file type in copied application PVC")
    return inventory


def copy_files(root, destination, pvcs, deadline=None, *, checksum=False):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for relative in pvcs:
        source = pvc_path(root, relative)
        target = destination / relative
        if (
            target.is_symlink()
            or target.parent.is_symlink()
            or not target.resolve().is_relative_to(destination.resolve())
        ):
            raise ValueError("capture destination redirects outside selected PVC")
        target.mkdir(parents=True, exist_ok=True, mode=0o700)
        timeout = remaining(deadline)
        subprocess.run(
            [
                "rsync",
                "--archive",
                *(["--checksum"] if checksum else []),
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
        if checksum and copy_inventory(source, deadline) != copy_inventory(
            target, deadline
        ):
            raise ValueError("copied destination content differs from stopped source")


def fsync_directory(path):
    remaining()
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(source, target, *, registry=None, apps=None, credentials=None):
    source, target = Path(source), Path(target)
    manifest = source / ".home-ops/manifest.json"
    if not manifest.is_file() or target.exists():
        raise ValueError(
            "generation requires a manifest and a new immutable destination"
        )
    metadata = json.loads(manifest.read_text())
    verify_manifest(
        source, metadata, registry=registry, apps=apps, credentials=credentials
    )
    created_parents = []
    ancestor = target.parent
    while not ancestor.exists():
        created_parents.append(ancestor)
        ancestor = ancestor.parent
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    entries = list(source.rglob("*"))
    for path in entries:
        if path.is_file() and not path.is_symlink():
            remaining()
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
    directories = [
        source,
        *[path for path in entries if path.is_dir() and not path.is_symlink()],
    ]
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        fsync_directory(directory)
    # Persist newly created destination ancestry before exposing the generation.
    for directory in created_parents:
        fsync_directory(directory)
    if created_parents:
        fsync_directory(ancestor)
    remaining()
    source.rename(target)
    for parent in dict.fromkeys([source.parent, target.parent]):
        fsync_directory(parent)
    return digest(target / ".home-ops/manifest.json")


def prune_generations(root):
    """Call under capture Lease; upload claims must be registered before release.

    Pending/failed generations and active claims are never garbage collected.
    Receipts and claims live outside read-only immutable generations.
    """
    root = Path(root)
    if not root.exists():
        return
    completed = []
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        if (root.parent / "uploads" / (path.name + ".json")).exists():
            continue
        receipt = root.parent / "uploaded" / (path.name + ".json")
        if receipt.is_symlink() or not receipt.is_file():
            continue
        try:
            metadata = json.loads(receipt.read_text())
            if not re.fullmatch("[a-f0-9]{64}", metadata.get("snapshot", "")) or digest(
                path / ".home-ops/manifest.json"
            ) != metadata.get("manifest_sha256"):
                continue
        except OSError, ValueError, TypeError:
            continue
        completed.append((path, receipt))
    completed.sort(key=lambda item: item[1].stat().st_mtime_ns)
    for path, receipt in completed[:-2]:
        shutil.rmtree(path)
        receipt.unlink()


def release_upload_claim(staging, operation, job_uid):
    """Caller proves terminal Job/Pods under the Lease; bind the durable receipt."""
    if not re.fullmatch("[a-z0-9][a-z0-9-]{0,51}", operation) or not job_uid:
        raise ValueError("exact upload actor required")
    staging = Path(staging)
    claim_path = staging / "uploads" / (operation + ".json")
    receipt_path = staging / "uploaded" / (operation + ".json")
    if any(
        path.is_symlink() or not path.is_file() for path in [claim_path, receipt_path]
    ):
        raise ValueError("verified external upload receipt required")
    claim, receipt = (
        json.loads(path.read_text()) for path in [claim_path, receipt_path]
    )
    if (
        claim.get("operation") != operation
        or claim.get("upload_job", {}).get("uid") != job_uid
        or receipt.get("status") != "ok"
        or receipt.get("operation") != operation
        or receipt.get("manifest_sha256") != claim.get("manifest_sha256")
        or not re.fullmatch("[a-f0-9]{64}", receipt.get("snapshot", ""))
    ):
        raise ValueError("upload claim differs from verified actor or receipt")
    claim_path.unlink()
    descriptor = os.open(claim_path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["preseed", "final", "publish", "cleanup", "claims", "release-claim"],
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--apps", required=True)
    parser.add_argument("--root", default="/data/appdata")
    parser.add_argument("--staging", default="/staging")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--database-bytes", type=int)
    parser.add_argument("--redis-bytes", type=int)
    parser.add_argument("--credentials", default="/run/credentials")
    parser.add_argument("--job-uid")
    args = parser.parse_args()
    if not args.operation or not all(c.isalnum() or c == "-" for c in args.operation):
        parser.error("invalid operation identity")
    registry = yaml.safe_load(Path(args.registry).read_text())
    consumers = select_consumers(registry, args.apps.split(","))
    if args.deadline is None and args.action == "preseed":
        args.deadline = time.time() + 600
    if args.deadline is not None:
        os.environ["HOME_OPS_DATA_DEADLINE"] = str(args.deadline)
    manifest_sha256 = None
    pvcs = [pvc for app in consumers.values() for pvc in app["pvcs"]]
    stage = Path(args.staging)
    if args.action == "claims":
        claims = []
        for path in sorted((stage / "uploads").glob("*.json")):
            if path.is_symlink() or not path.is_file():
                raise ValueError("upload claim must be a private regular file")
            claim = json.loads(path.read_text())
            if path.name != claim.get("operation", "") + ".json":
                raise ValueError("upload claim identity differs from its path")
            if claim.get("upload_job") and (stage / "uploaded" / path.name).is_file():
                claims.append(claim)
        print(json.dumps(claims))
        return
    if args.action == "release-claim":
        release_upload_claim(stage, args.operation, args.job_uid)
        return
    progress = stage / "in-progress" / args.operation
    target = stage / "generations" / args.operation
    if args.action == "preseed":
        if (
            any(app["backend"] == "postgresql" for app in consumers.values())
            and (args.database_bytes is None or args.database_bytes <= 0)
            or any(uses_shared_redis(app) for app in consumers.values())
            and (args.redis_bytes is None or args.redis_bytes <= 0)
        ):
            raise ValueError("database/RDB size estimates required before preseed")
        stage.mkdir(parents=True, exist_ok=True, mode=0o700)
        prune_generations(stage / "generations")
        if progress.exists() or target.exists():
            raise ValueError("operation staging already exists")
        if shutil.disk_usage(stage).free < required_bytes(
            args.root,
            pvcs,
            database_bytes=args.database_bytes or 0,
            redis_bytes=args.redis_bytes or 0,
        ):
            raise ValueError(
                "insufficient staging space for two generations plus twenty percent"
            )
        copy_files(args.root, progress, pvcs, args.deadline)
    elif args.action == "final":
        if args.deadline is None:
            raise ValueError(
                "final capture requires the stopped-writer absolute deadline"
            )
        if not progress.is_dir():
            raise ValueError("online preseed required")
        copy_files(args.root, progress, pvcs, args.deadline, checksum=True)
    elif args.action == "publish":
        manifest_sha256 = publish(
            progress,
            target,
            registry=registry,
            apps=args.apps.split(","),
            credentials=args.credentials,
        )
    else:
        prune_generations(stage / "generations")
    print(
        json.dumps(
            {
                "status": "ok",
                "operation": args.operation,
                "generation": str(target),
                "manifest_sha256": manifest_sha256,
            }
        )
    )


if __name__ == "__main__":
    main()
