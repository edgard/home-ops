"""Stage and validate registered recovery; Kubernetes I/O stays in the role."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from copy import copy, deepcopy
from datetime import datetime
from pathlib import Path

import yaml
from capture import copy_files, copy_inventory, pvc_path
from data_tools import (
    remaining,
    restore_postgres,
    select_consumers,
    transfer_redis,
    uses_shared_redis,
    validate_registry,
    verify_manifest,
    verify_sqlite,
)


def run(command):
    result = subprocess.run(
        command, capture_output=True, check=False, timeout=remaining(default=7200)
    )
    if result.returncode:
        raise ValueError(
            "Recovery command failed; selected application remains unchanged or held for inspection"
        )
    return result.stdout


def historical_tags(row):
    return not any(tag.startswith("appdata-consumer-") for tag in row.get("tags", []))


def choose_snapshot(rows, requested, root, *, apps=(), allow_historical=False):
    if requested != "latest" and not re.fullmatch("[a-f0-9]{8,64}", requested):
        raise ValueError("Use latest or an immutable snapshot ID")
    candidates = [
        row
        for row in rows
        if row.get("hostname") == "homelab"
        and root in row.get("paths", [])
        and "appdata" in row.get("tags", [])
        and "appdata-pending" not in row.get("tags", [])
        and (
            requested != "latest"
            or all("appdata-consumer-" + app in row.get("tags", []) for app in apps)
            or allow_historical
            and historical_tags(row)
        )
    ]
    if requested == "latest":
        if not candidates:
            raise ValueError("No complete canonical application snapshot")
        selected = max(candidates, key=lambda row: datetime.fromisoformat(row["time"]))
    else:
        candidates = [row for row in candidates if row["id"].startswith(requested)]
        if len(candidates) != 1:
            raise ValueError(
                "Snapshot ID missing, ambiguous, pending, or outside the appdata family"
            )
        selected = candidates[0]
    if not re.fullmatch("[a-f0-9]{64}", selected.get("id", "")):
        raise ValueError("Snapshot identity is incomplete")
    return selected["id"]


def restore_consumers(registry, apps):
    validate_registry(registry)
    registered = {**registry["consumers"], **registry.get("file_consumers", {})}
    if (
        not apps
        or len(apps) != len(set(apps))
        or any(app not in registered for app in apps)
    ):
        raise ValueError("Nonempty unique registered recovery selection required")
    return {app: registered[app] for app in apps}


def file_mapping(app):
    return {
        "namespace": app["namespace"],
        "pvcs": list(app["pvcs"]),
        "backend": app.get("backend", "files"),
        "sqlite_files": list(app.get("sqlite_files", [])),
        "mode": "live-files",
    }


def recovery_scope(manifest, registry, apps):
    consumers = restore_consumers(registry, apps)
    native, legacy = {}, {}
    if manifest is not None and (
        not isinstance(manifest, dict)
        or manifest.get("version") != 1
        or not isinstance(manifest.get("consumers"), dict)
        or not isinstance(manifest.get("files"), dict)
        or not isinstance(manifest.get("symlinks", {}), dict)
        or not isinstance(manifest.get("legacy_consumers", {}), dict)
    ):
        raise ValueError("Compatible modern recovery manifest required")
    for name, app in consumers.items():
        captured = manifest.get("consumers", {}) if manifest is not None else {}
        if name in captured:
            if name not in registry["consumers"] or name in manifest.get(
                "legacy_consumers", {}
            ):
                raise ValueError("Conflicting native and legacy manifest mapping")
            native[name] = app
        else:
            if app.get("backend") == "postgresql" or uses_shared_redis(app):
                raise ValueError(
                    "Selected PostgreSQL/Redis application requires a compatible database manifest"
                )
            expected = file_mapping(app)
            if (
                manifest is not None
                and manifest.get("legacy_consumers", {}).get(name) != expected
            ):
                raise ValueError(
                    "Selected legacy application requires its captured registered PVC mapping"
                )
            legacy[name] = expected
    if native:
        selected_manifest(manifest, registry, list(native))
    return native, legacy


def selected_manifest(manifest, registry, apps):
    consumers = select_consumers(registry, apps)
    if manifest.get("version") != 1 or not set(consumers) <= set(
        manifest.get("consumers", {})
    ):
        raise ValueError(
            "Selected PostgreSQL application requires a compatible database manifest"
        )
    for name, app in consumers.items():
        data = manifest["consumers"][name]
        expected_redis = (
            {"database": app["redis"]["database"]} if uses_shared_redis(app) else None
        )
        databases = app.get("databases", []) if app["backend"] == "postgresql" else []
        if (
            data.get("backend") != app["backend"]
            or data.get("databases") != databases
            or data.get("pvcs") != app["pvcs"]
            or data.get("redis") != expected_redis
            or data.get("key_refs", []) != app.get("key_refs", [])
        ):
            raise ValueError(
                "Selected application requires a compatible database manifest and registry mapping"
            )
        required = [
            app["pvcs"][0] + "/.home-ops/databases/" + db["name"] + ".dump"
            for db in databases
        ]
        if app["backend"] == "sqlite":
            required.extend(app.get("sqlite_files", []))
        if expected_redis:
            required.append(".home-ops/redis.rdb")
        if any(path not in manifest.get("files", {}) for path in required):
            raise ValueError(
                "Selected application requires complete database payload inventory"
            )
    result = deepcopy(manifest)
    result["consumers"] = {app: result["consumers"][app] for app in consumers}
    prefixes = [pvc + "/" for app in consumers.values() for pvc in app["pvcs"]]
    needs_redis = any(uses_shared_redis(app) for app in consumers.values())
    result["files"] = {
        path: value
        for path, value in result.get("files", {}).items()
        if any(path.startswith(prefix) for prefix in prefixes)
        or (needs_redis and path == ".home-ops/redis.rdb")
    }
    result["symlinks"] = {
        path: value
        for path, value in result.get("symlinks", {}).items()
        if any(path.startswith(prefix) for prefix in prefixes)
    }
    return result


def operation_path(args):
    if not re.fullmatch("[a-z0-9][a-z0-9-]{0,62}", args.operation):
        raise ValueError("Invalid recovery operation identity")
    base = Path(args.staging).resolve()
    path = base / "restores" / args.operation
    if path.is_symlink() or not path.resolve().is_relative_to(base):
        raise ValueError("Recovery staging redirects outside its root")
    return path


def legacy_inventory(root, consumers):
    inventory = {}
    for app in consumers.values():
        for pvc in app["pvcs"]:
            directory = pvc_path(root, pvc)
            for path in directory.rglob("*"):
                if path.is_symlink() and (
                    Path(path.readlink()).is_absolute()
                    or not path.resolve().is_relative_to(directory)
                ):
                    raise ValueError(
                        "Legacy symlink redirects outside its selected PVC"
                    )
            inventory[pvc] = copy_inventory(directory, None)
        for relative in app["sqlite_files"]:
            source = Path(root) / relative
            if not source.is_file() or source.is_symlink():
                raise ValueError("Required legacy SQLite database missing")
            verify_sqlite(source)
    # JSON normalizes inventory tuples for durable metadata comparisons.
    return json.loads(json.dumps(inventory))


def evidence_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def selection_digest(metadata):
    return hashlib.sha256(
        json.dumps(
            {
                key: value
                for key, value in metadata.items()
                if key != "selection_sha256"
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def verify_selected(root, manifest, registry, args, images=None):
    native, legacy = recovery_scope(manifest, registry, args.apps)
    if native:
        verify_manifest(
            root,
            selected_manifest(manifest, registry, list(native)),
            json.loads(args.images) if images is None else images,
            registry=registry,
            apps=list(native),
            credentials=args.credentials,
        )
    return legacy, legacy_inventory(root, legacy)


def stage(args, registry):
    consumers = restore_consumers(registry, args.apps)
    root = args.snapshot_root.rstrip("/")
    if not root.startswith("/") or not root or ".." in Path(root).parts:
        raise ValueError("An absolute non-root snapshot path is required")
    rows = json.loads(
        run(
            [
                "restic",
                "snapshots",
                "--json",
                "--host",
                "homelab",
                "--tag",
                "appdata",
                "--path",
                root,
            ]
        )
    )
    allow_historical = all(
        app.get("backend") != "postgresql" and not uses_shared_redis(app)
        for app in consumers.values()
    )
    snapshot = choose_snapshot(
        rows, args.snapshot, root, apps=args.apps, allow_historical=allow_historical
    )
    row = next(row for row in rows if row["id"] == snapshot)
    manifest_path = root + "/.home-ops/manifest.json"
    nodes = [
        json.loads(line)
        for line in run(
            [
                "restic",
                "ls",
                "--json",
                snapshot,
                manifest_path,
            ]
        ).splitlines()
        if line.strip()
    ]
    manifest_nodes = [node for node in nodes if node.get("path") == manifest_path]
    raw, manifest = None, None
    if manifest_nodes:
        if len(manifest_nodes) != 1 or manifest_nodes[0].get("type") != "file":
            raise ValueError("Modern recovery manifest must be a regular file")
        raw = run(["restic", "dump", snapshot, manifest_path])
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("Present recovery manifest must be a JSON object")
    elif not allow_historical or not historical_tags(row):
        raise ValueError("Modern/PostgreSQL snapshot requires its compatible manifest")
    native, legacy = recovery_scope(manifest, registry, args.apps)
    destination = operation_path(args)
    if destination.exists():
        raise ValueError(
            "Recovery operation staging already exists; preserve failed inspection data"
        )
    destination.mkdir(parents=True, mode=0o700)
    command = [
        "restic",
        "--retry-lock",
        "30m",
        "restore",
        snapshot,
        "--target",
        str(destination),
        "--exclude-xattr",
        "*",
    ]
    for consumer in consumers.values():
        for pvc in consumer["pvcs"]:
            command.extend(["--include", root + "/" + pvc])
    if raw is not None:
        command.extend(["--include", manifest_path])
    if any(uses_shared_redis(consumer) for consumer in native.values()):
        command.extend(["--include", root + "/.home-ops/redis.rdb"])
    run(command)
    restored = destination / root.lstrip("/")
    if raw is not None and (restored / ".home-ops/manifest.json").read_bytes() != raw:
        raise ValueError(
            "Staged snapshot manifest differs from selected immutable snapshot"
        )
    legacy, inventory = verify_selected(restored, manifest, registry, args)
    metadata = {
        "operation": args.operation,
        "snapshot": snapshot,
        "manifest_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "root": str(restored),
        "apps": args.apps,
        "compatibility": "modern-manifest"
        if raw is not None
        else "historical-live-files",
        "legacy_consumers": legacy,
        "legacy_inventory_sha256": evidence_digest(inventory),
    }
    metadata["selection_sha256"] = selection_digest(metadata)
    (destination / "recovery.json").write_text(json.dumps(metadata) + "\n")
    return metadata


def validate(args, registry, images=None):
    directory = operation_path(args)
    metadata = json.loads((directory / "recovery.json").read_text())
    if metadata.get("operation") != args.operation or metadata.get("apps") != args.apps:
        raise ValueError(
            "Recovery staging belongs to another operation or application scope"
        )
    if "selection_sha256" in metadata:
        actual = selection_digest(metadata)
        if actual != metadata["selection_sha256"] or getattr(
            args, "selection_sha256", None
        ) not in {None, actual}:
            raise ValueError(
                "Recovery selection evidence changed after journal binding"
            )
    elif metadata.get("legacy_consumers") or not metadata.get("manifest_sha256"):
        raise ValueError("Legacy recovery requires bound selection evidence")
    root = Path(metadata["root"])
    expected_root = directory / args.snapshot_root.lstrip("/")
    if (
        root != expected_root
        or root.is_symlink()
        or not root.resolve().is_relative_to(directory)
    ):
        raise ValueError("Staged recovery root is invalid")
    manifest = None
    if metadata.get("manifest_sha256"):
        path = root / ".home-ops/manifest.json"
        if path.is_symlink():
            raise ValueError("Recovery manifest must not redirect")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata["manifest_sha256"] or getattr(
            args, "manifest_sha256", None
        ) not in {None, metadata["manifest_sha256"]}:
            raise ValueError("Recovery manifest changed after selection")
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("Present recovery manifest must be a JSON object")
    elif (
        metadata.get("compatibility") != "historical-live-files"
        or (root / ".home-ops/manifest.json").exists()
    ):
        raise ValueError("Historical recovery selection changed")
    legacy, inventory = verify_selected(root, manifest, registry, args, images)
    if legacy != metadata.get("legacy_consumers", {}) or evidence_digest(
        inventory
    ) != metadata.get("legacy_inventory_sha256", evidence_digest({})):
        raise ValueError("Legacy mapping or payload changed after snapshot staging")
    return metadata


def restore_files(args, registry):
    metadata = validate(args, registry)
    if metadata.get("legacy_consumers") and not getattr(args, "selection_sha256", None):
        raise ValueError(
            "Legacy file replacement requires journal-bound selection evidence"
        )
    consumers = restore_consumers(registry, args.apps)
    pvcs = [pvc for app in consumers.values() for pvc in app["pvcs"]]
    for pvc in pvcs:
        pvc_path(args.live_root, pvc)
    copy_files(metadata["root"], args.live_root, pvcs, checksum=True)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["stage", "validate", "files", "postgres", "redis"]
    )
    parser.add_argument(
        "--registry",
        default="/opt/home-ops/ansible/roles/shared_data/files/registry.yaml",
    )
    parser.add_argument("--apps", required=True, type=lambda value: value.split(","))
    parser.add_argument("--snapshot", default="latest")
    parser.add_argument("--snapshot-root", default="/data/appdata")
    parser.add_argument("--staging", default="/staging")
    parser.add_argument("--live-root", default="/data/appdata")
    parser.add_argument("--operation", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--credentials", default="/run/credentials")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--selection-sha256")
    parser.add_argument(
        "--pg-host", default="postgresql.platform-system.svc.cluster.local"
    )
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument(
        "--redis-host", default="redis.platform-system.svc.cluster.local"
    )
    parser.add_argument("--redis-port", type=int, default=6379)
    parser.add_argument(
        "--redis-source-host", default="redis-recovery.selfhosted.svc.cluster.local"
    )
    parser.add_argument("--redis-source-port", type=int, default=6379)
    parser.add_argument("--redis-source-credentials")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    registry = yaml.safe_load(Path(args.registry).read_text())
    if args.action in {"files", "postgres", "redis"}:
        if not args.confirm:
            parser.error("Live data replacement requires confirmed held recovery")
        if not args.manifest_sha256 and not args.selection_sha256:
            parser.error(
                "Live data replacement requires journal-bound selection evidence"
            )
    if args.action == "stage":
        result = stage(args, registry)
    elif args.action == "validate":
        result = validate(
            args, registry, json.loads(args.images) if args.images != "{}" else None
        )
    elif args.action == "files":
        result = restore_files(args, registry)
    else:
        result = validate(args, registry)
        if result.get("legacy_consumers") and not args.selection_sha256:
            parser.error(
                "Legacy data replacement requires selected evidence SHA256 from the journal"
            )
        native_args = copy(args)
        native_args.root = result["root"]
        native_args.apps = [app for app in args.apps if app in registry["consumers"]]
        if native_args.apps:
            if args.action == "postgres":
                restore_postgres(native_args, registry)
            else:
                transfer_redis(native_args, registry)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(
            json.dumps({"status": "failed", "error_type": type(error).__name__}),
            file=sys.stderr,
        )
        sys.exit(1)
