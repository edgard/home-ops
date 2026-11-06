"""Upload an exact generation and promote only after remote payload verification."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import Timer

import yaml
from data_tools import (
    NAME,
    digest,
    legacy_consumers,
    remaining,
    successful_snapshot,
    verify_manifest,
)
from data_tools import legacy_pvcs as expected_legacy_pvcs


def run_native(command):
    result = subprocess.run(
        command,
        env={**os.environ, "TZ": "UTC"},
        capture_output=True,
        text=True,
        timeout=remaining(default=7200),
        check=False,
    )
    return result.returncode, result.stdout


def checked(run, command):
    code, output = run(command)
    if code:
        raise ValueError("Restic metadata operation failed; snapshot remains pending")
    return output


def stream_digest(command):
    """Stream SHA256 with constant memory and a wall-clock subprocess deadline."""
    result = hashlib.sha256()
    budget = remaining(default=7200)
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    ) as process:
        timer = Timer(budget, process.kill)
        timer.start()
        try:
            for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                result.update(block)
            if process.wait():
                raise ValueError(
                    "Restic payload verification failed; snapshot remains pending"
                )
        finally:
            timer.cancel()
    return result.hexdigest()


def validate_legacy_pvcs(root, manifest, legacy_pvcs):
    selected = {pvc for app in manifest["consumers"].values() for pvc in app["pvcs"]}
    reserved = {
        "platform-system/postgresql",
        "platform-system/redis",
        "selfhosted/shared-data-staging",
    }
    if len(legacy_pvcs) != len(set(legacy_pvcs)):
        raise ValueError("duplicate legacy PVC allowlist")
    for pvc in legacy_pvcs:
        if (
            len(pvc.split("/")) != 2
            or not all(NAME.fullmatch(part) for part in pvc.split("/"))
            or pvc in selected
            or pvc in reserved
        ):
            raise ValueError(
                "legacy PVC overlaps selected generation or has an unsafe/infra path"
            )
        path = Path(root) / pvc
        if (
            not path.is_dir()
            or path.is_symlink()
            or path.parent.is_symlink()
            or not path.resolve().is_relative_to(Path(root).resolve())
        ):
            raise ValueError(
                "legacy PVC is missing or redirects outside canonical root"
            )


def excluded_paths(root, manifest, legacy_pvcs=()):
    """Capture selected staged PVCs and only explicitly allowlisted legacy live PVCs."""
    allowed = {}
    for consumer in manifest["consumers"].values():
        for pvc in consumer["pvcs"]:
            namespace, name = pvc.split("/")
            allowed.setdefault(namespace, set()).add(name)
    for pvc in legacy_pvcs:
        namespace, name = pvc.split("/")
        allowed.setdefault(namespace, set()).add(name)
    excluded = []
    for path in Path(root).iterdir():
        if path.name == ".home-ops":
            for metadata in path.iterdir():
                if metadata.name not in {"manifest.json", "redis.rdb"}:
                    excluded.append(str(metadata))
        elif path.name not in allowed:
            excluded.append(str(path))
        else:
            if path.is_symlink() or not path.is_dir():
                raise ValueError("canonical namespace mount is invalid")
            excluded.extend(
                str(child)
                for child in path.iterdir()
                if child.name not in allowed[path.name]
            )
    return excluded


def remote_inventory(run, snapshot, root, manifest, legacy_pvcs=()):
    rows = [
        json.loads(line)
        for line in checked(
            run, ["restic", "ls", "--json", "--recursive", snapshot, root]
        ).splitlines()
        if line.strip()
    ]
    files, links = {}, {}
    for row in rows:
        if row.get("struct_type") != "node" or row.get("type") == "dir":
            continue
        path = row.get("path", "")
        if not path.startswith(root + "/"):
            raise ValueError("uploaded path lies outside canonical root")
        relative = path[len(root) + 1 :]
        if any(relative.startswith(pvc + "/") for pvc in legacy_pvcs):
            if row.get("type") not in {"file", "symlink"}:
                raise ValueError("unsupported legacy uploaded node type")
            continue
        if row.get("type") == "file":
            files[relative] = row
        elif row.get("type") == "symlink":
            links[relative] = row.get("linktarget")
        else:
            raise ValueError("unsupported uploaded node type")
    if set(files) != set(manifest["files"]) | {
        ".home-ops/manifest.json"
    } or links != manifest.get("symlinks", {}):
        raise ValueError("uploaded path inventory differs from immutable generation")


def upload(
    operation,
    manifest,
    run=run_native,
    *,
    root="/data/appdata",
    generation_root=None,
    manifest_sha256,
    registry=None,
    apps=None,
    credentials=None,
    hash_remote=stream_digest,
    legacy_pvcs=(),
):
    root = str(Path(root))
    generation_root = Path(generation_root if generation_root is not None else root)
    if (
        not Path(root).is_absolute()
        or root == "/"
        or not re.fullmatch("[a-f0-9]{64}", manifest_sha256)
    ):
        raise ValueError(
            "absolute canonical root and exact capture manifest SHA256 required"
        )
    validate_legacy_pvcs(root, manifest, legacy_pvcs)
    if registry is not None and sorted(legacy_pvcs) != expected_legacy_pvcs(
        registry, apps or list(manifest["consumers"])
    ):
        raise ValueError(
            "legacy upload scope differs from source-owned consumer registry"
        )
    if registry is not None and manifest.get(
        "legacy_consumers", {}
    ) != legacy_consumers(registry, apps or list(manifest["consumers"])):
        raise ValueError("legacy capture mapping differs from source-owned registry")
    if manifest.get("operation") != operation:
        raise ValueError("generation operation differs from journal")
    captured = datetime.fromisoformat(manifest["captured_at"])
    if captured.tzinfo is None:
        raise ValueError("capture time must include a timezone")
    for location in {generation_root, Path(root)}:
        path = location / ".home-ops/manifest.json"
        if (
            path.is_symlink()
            or digest(path) != manifest_sha256
            or json.loads(path.read_bytes()) != manifest
        ):
            raise ValueError("mounted generation manifest differs from journal capture")
        verify_manifest(
            location, manifest, registry=registry, apps=apps, credentials=credentials
        )
    command = [
        "restic",
        "--retry-lock",
        "30m",
        "backup",
        root,
        "--host",
        "homelab",
        "--tag",
        "appdata-pending",
        "--time",
        captured.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"),
        "--json",
    ]
    covered_apps = set(manifest["consumers"])
    if registry is not None:
        for name, app in {
            **registry["consumers"],
            **registry.get("file_consumers", {}),
        }.items():
            if app.get("pvcs") and set(app["pvcs"]) <= set(legacy_pvcs):
                covered_apps.add(name)
    for app in sorted(covered_apps):
        command.extend(["--tag", "appdata-consumer-" + app])
    for path in excluded_paths(root, manifest, legacy_pvcs):
        command.extend(["--exclude", path])
    code, output = run(command)
    snapshot = successful_snapshot(
        code, [json.loads(line) for line in output.splitlines() if line.strip()]
    )
    stored = checked(
        run, ["restic", "dump", snapshot, root + "/.home-ops/manifest.json"]
    ).encode()
    if hashlib.sha256(stored).hexdigest() != manifest_sha256:
        raise ValueError("uploaded generation manifest does not match capture SHA256")
    remote_inventory(run, snapshot, root, manifest, legacy_pvcs)
    # Stream every payload, including files: hashes are stronger than trusting restic ls.
    for relative, expected in manifest["files"].items():
        if hash_remote(["restic", "dump", snapshot, root + "/" + relative]) != expected:
            raise ValueError(
                "uploaded payload checksum differs; snapshot remains pending"
            )
    before = json.loads(checked(run, ["restic", "snapshots", "--json", snapshot]))
    if (
        len(before) != 1
        or not before[0].get("tree")
        or "appdata-pending" not in before[0].get("tags", [])
    ):
        raise ValueError("pending snapshot metadata missing")
    checked(
        run,
        ["restic", "tag", "--add", "appdata", "--remove", "appdata-pending", snapshot],
    )
    candidates = json.loads(
        checked(
            run,
            [
                "restic",
                "snapshots",
                "--json",
                "--host",
                "homelab",
                "--path",
                root,
                "--tag",
                "appdata",
            ],
        )
    )
    promoted = [
        item
        for item in candidates
        if item.get("tree") == before[0]["tree"]
        and item.get("original")
        == before[0].get("original", before[0].get("id", snapshot))
        and "appdata" in item.get("tags", [])
        and "appdata-pending" not in item.get("tags", [])
    ]
    if len(promoted) != 1:
        raise ValueError("could not verify promoted snapshot identity")
    return promoted[0]["id"]


def write_receipt(path, manifest, manifest_sha256, snapshot):
    """Publish success outside the immutable generation, after remote verification."""
    if not re.fullmatch("[a-f0-9]{64}", snapshot):
        raise ValueError("complete verified snapshot identity required")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = {
        "status": "ok",
        "snapshot": snapshot,
        "operation": manifest["operation"],
        "manifest_sha256": manifest_sha256,
        "captured_at": manifest["captured_at"],
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(metadata, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/data/appdata")
    parser.add_argument("--generation-root", default="/generation")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--legacy-pvc", action="append", default=[])
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--registry",
        default="/opt/home-ops/ansible/roles/shared_data/files/registry.yaml",
    )
    parser.add_argument("--credentials", default="/run/credentials")
    parser.add_argument("--apps", required=True, type=lambda value: value.split(","))
    args = parser.parse_args()
    manifest = json.loads(
        (Path(args.generation_root) / ".home-ops/manifest.json").read_text()
    )
    registry = yaml.safe_load(Path(args.registry).read_text())
    snapshot = upload(
        args.operation,
        manifest,
        root=args.root,
        generation_root=args.generation_root,
        manifest_sha256=args.manifest_sha256,
        registry=registry,
        apps=args.apps,
        credentials=args.credentials,
        legacy_pvcs=args.legacy_pvc,
    )
    print(
        json.dumps(
            write_receipt(args.receipt, manifest, args.manifest_sha256, snapshot)
        )
    )


if __name__ == "__main__":
    main()
