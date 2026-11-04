"""Upload a verified generation without making partial snapshots recoverable."""

import argparse
import json
import subprocess
from pathlib import Path

import yaml
from data_tools import successful_snapshot, verify_manifest


def run_native(command):
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=7200, check=False
    )
    return result.returncode, result.stdout


def checked(run, command):
    code, output = run(command)
    if code:
        raise ValueError("Restic metadata operation failed; snapshot remains pending")
    return output


def upload(operation, manifest, run=run_native, *, root="/data/appdata"):
    code, output = run(
        [
            "restic",
            "--retry-lock",
            "30m",
            "backup",
            root,
            "--host",
            "homelab",
            "--tag",
            "appdata-pending",
            "--json",
            "--exclude",
            root + "/platform-system/postgresql",
            "--exclude",
            root + "/platform-system/redis",
            "--exclude",
            root + "/selfhosted/shared-data-staging",
        ]
    )
    snapshot = successful_snapshot(
        code, [json.loads(line) for line in output.splitlines() if line.strip()]
    )
    stored = json.loads(
        checked(run, ["restic", "dump", snapshot, root + "/.home-ops/manifest.json"])
    )
    if stored != manifest or manifest.get("operation") != operation:
        raise ValueError("uploaded generation manifest does not match capture")
    before = json.loads(checked(run, ["restic", "snapshots", "--json", snapshot]))
    if len(before) != 1 or not before[0].get("tree"):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/generation")
    parser.add_argument("--operation", required=True)
    parser.add_argument(
        "--registry",
        default="/opt/home-ops/ansible/roles/shared_data/files/registry.yaml",
    )
    parser.add_argument("--apps", type=lambda value: value.split(","))
    args = parser.parse_args()
    manifest = json.loads((Path(args.root) / ".home-ops/manifest.json").read_text())
    registry = yaml.safe_load(Path(args.registry).read_text())
    verify_manifest(args.root, manifest, registry=registry, apps=args.apps)
    snapshot = upload(args.operation, manifest)
    print(
        json.dumps({"status": "ok", "snapshot": snapshot, "operation": args.operation})
    )


if __name__ == "__main__":
    main()
