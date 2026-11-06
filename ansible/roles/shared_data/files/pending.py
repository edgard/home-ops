"""Separately inspect or remove abandoned unpromoted Restic snapshots."""

import argparse
import json
import re
from datetime import UTC, datetime

from upload import checked, run_native


def cleanup(root, *, now=None, confirm=False, run=run_native):
    """Caller must fence upload actors under the maintenance Lease before deletion."""
    now = datetime.now(UTC).timestamp() if now is None else float(now)
    snapshots = json.loads(
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
                "appdata-pending",
            ],
        )
    )
    selected = []
    for snapshot in snapshots:
        tags = snapshot.get("tags", [])
        if "appdata" in tags or "appdata-pending" not in tags:
            continue
        if snapshot.get("hostname") != "homelab" or snapshot.get("paths") != [root]:
            continue
        captured = datetime.fromisoformat(snapshot["time"].replace("Z", "+00:00"))
        if captured.tzinfo is None or not re.fullmatch("[a-f0-9]{64}", snapshot["id"]):
            raise ValueError(
                "Invalid pending snapshot metadata; inspect without deletion"
            )
        if now - captured.timestamp() >= 7 * 86400:
            selected.append(snapshot["id"])
    if confirm and selected:
        checked(run, ["restic", "forget", *selected])
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/data/appdata")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "forgotten" if args.confirm else "candidates": cleanup(
                    args.root, confirm=args.confirm
                )
            }
        )
    )


if __name__ == "__main__":
    main()
