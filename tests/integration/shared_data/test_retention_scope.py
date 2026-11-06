"""Existing retention must leave pending uploads for separate inspected cleanup."""

import json
import shlex
import subprocess
from datetime import UTC, datetime

import yaml

from tests.support.runtime import ROOT

from .test_upload_acceptance import repository as repository


def test_real_retention_keeps_all_pending_and_expires_every_repository_family(
    repository, tmp_path
):
    path = tmp_path / "data"
    path.write_text("synthetic")
    families = [
        ("homelab", ["appdata", "appdata-consumer-demo"]),
        ("homelab", ["appdata", "appdata-consumer-other"]),
        ("edgards-mini", ["documents"]),
        ("edgard-desktop", ["documents"]),
        ("future-client", ["another-family"]),
        ("homelab", ["appdata-pending"]),
    ]
    ids = {}
    # Eighteen old annual snapshots exceed every ordinary retention count.
    # Pending snapshots must survive even when they would otherwise expire.
    for host, tags in families:
        ids[host, tuple(tags)] = set()
        for year in range(2000, 2018):
            command = [
                "restic",
                "backup",
                str(path),
                "--host",
                host,
                "--time",
                f"{year}-01-01 00:00:00",
                "--json",
            ]
            for tag in tags:
                command += ["--tag", tag]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            ids[host, tuple(tags)].add(
                next(
                    json.loads(line)["snapshot_id"]
                    for line in result.stdout.splitlines()
                    if json.loads(line).get("message_type") == "summary"
                )
            )
    script = yaml.safe_load((ROOT / "apps/selfhosted/restic/values.yaml").read_text())[
        "controllers"
    ]["maintenance"]["containers"]["app"]["command"][-1]
    commands = [
        shlex.split(line)
        for line in script.replace("\\\n", " ").splitlines()
        if line.strip()
    ]
    command = next(
        command
        for command in commands
        if command[0] == "restic" and "forget" in command
    )
    result = subprocess.run(
        command + ["--dry-run", "--json"], capture_output=True, text=True, check=True
    )
    groups = json.loads(result.stdout)
    by_family = {(group["host"], tuple(group["tags"])): group for group in groups}
    assert set(by_family) == set(ids), result.stdout
    pending = ("homelab", ("appdata-pending",))
    for family, snapshot_ids in ids.items():
        group = by_family[family]
        kept = {snapshot["id"] for snapshot in group["keep"] or []}
        removed = {snapshot["id"] for snapshot in group["remove"] or []}
        assert kept | removed == snapshot_ids
        if family == pending:
            assert kept == snapshot_ids
            assert removed == set()
        else:
            assert kept and removed, (family, group)

    # Prove the fixture would expire old pending snapshots without the exemption.
    ordinary = [arg for arg in command if arg not in {"--keep-tag", "appdata-pending"}]
    comparison = subprocess.run(
        ordinary + ["--dry-run", "--json"], capture_output=True, text=True, check=True
    )
    pending_group = next(
        group
        for group in json.loads(comparison.stdout)
        if group["host"] == "homelab" and group["tags"] == ["appdata-pending"]
    )
    assert pending_group["remove"]

    # Execute the unchanged source forget/prune command, then check actual IDs.
    subprocess.run(command, capture_output=True, text=True, check=True)
    retained = json.loads(
        subprocess.run(
            ["restic", "snapshots", "--json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert {snapshot["id"] for snapshot in retained} == {
        snapshot["id"] for group in groups for snapshot in group["keep"] or []
    }


def test_separate_cleanup_removes_only_old_unpromoted_pending(
    repository, tmp_path, adapters
):
    path = tmp_path / "payload"
    path.write_text("synthetic")
    now = datetime.now(UTC)
    cases = [
        ("old-pending", ["appdata-pending"], now.timestamp() - 8 * 86400),
        ("recent-pending", ["appdata-pending"], now.timestamp() - 3600),
        ("old-canonical", ["appdata"], now.timestamp() - 8 * 86400),
        ("ambiguous-tags", ["appdata", "appdata-pending"], now.timestamp() - 8 * 86400),
    ]
    ids = {}
    for name, tags, captured in cases:
        args = [
            "restic",
            "backup",
            str(path),
            "--host",
            "homelab",
            "--time",
            datetime.fromtimestamp(captured, UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "--json",
        ]
        for tag in tags:
            args += ["--tag", tag]
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        ids[name] = next(
            json.loads(line)["snapshot_id"]
            for line in result.stdout.splitlines()
            if json.loads(line).get("message_type") == "summary"
        )
    cleaner = adapters["pending"]
    plan = cleaner.cleanup(str(path), now=now.timestamp(), confirm=False)
    assert plan == [ids["old-pending"]]
    assert (
        len(
            json.loads(
                subprocess.run(
                    ["restic", "snapshots", "--json"],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
            )
        )
        == 4
    )
    assert cleaner.cleanup(str(path), now=now.timestamp(), confirm=True) == plan
    retained = {
        row["id"]
        for row in json.loads(
            subprocess.run(
                ["restic", "snapshots", "--json"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    }
    assert retained == set(ids.values()) - {ids["old-pending"]}


def test_pending_cleanup_holds_schedules_but_does_not_stop_application_writers(
    repository, tmp_path
):
    from tests.integration import test_data_maintenance as api
    from tests.support.runtime import PYTHON, run_role

    path = tmp_path / "payload"
    path.write_text("synthetic")
    now = datetime.now(UTC).timestamp()
    ids = {}
    for name, tags, age in [
        ("old-pending", ["appdata-pending"], 8 * 86400),
        ("recent-pending", ["appdata-pending"], 3600),
        ("old-canonical", ["appdata"], 8 * 86400),
    ]:
        command = [
            "restic",
            "backup",
            str(path),
            "--host",
            "homelab",
            "--json",
            "--time",
            datetime.fromtimestamp(now - age, UTC).strftime("%Y-%m-%d %H:%M:%S"),
        ]
        for tag in tags:
            command += ["--tag", tag]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        ids[name] = next(
            json.loads(line)["snapshot_id"]
            for line in result.stdout.splitlines()
            if json.loads(line).get("message_type") == "summary"
        )
    objects, variables = api.scenario_objects()
    with api.maintenance_api(tmp_path, objects) as (connection, state):
        result = run_role(
            tmp_path,
            "shared_data",
            "main",
            {
                **connection,
                **variables,
                "shared_data_action": "cleanup",
                "shared_data_python": str(PYTHON),
                "shared_data_apps": ["paperless"],
                "shared_data_snapshot_root": str(path),
            },
            env={
                "RESTIC_REPOSITORY": str(tmp_path / "repository"),
                "RESTIC_PASSWORD": "synthetic-only",
                "RESTIC_CACHE_DIR": str(tmp_path / "cache"),
            },
        )
        assert result.returncode == 0, result.stdout + result.stderr
        journal = json.loads(
            state["objects"][
                "/api/v1/namespaces/selfhosted/configmaps/shared-data-operation"
            ]["data"]["journal.json"]
        )
        assert journal["phase"] == "complete"
        assert not state["objects"][
            "/apis/coordination.k8s.io/v1/namespaces/selfhosted/leases/shared-data-operation"
        ]["spec"]["holderIdentity"]
        assert any(
            event["method"] == "PATCH"
            and "/cronjobs/export" in event["path"]
            and any(
                patch.get("path") == "/spec/suspend" and patch.get("value") is True
                for patch in event.get("body", [])
            )
            for event in state["events"]
        )
        for event in state["events"]:
            if event["method"] == "PATCH" and "/deployments/paperless" in event["path"]:
                assert not any(
                    patch.get("path") == "/spec/replicas" and patch.get("value") == 0
                    for patch in event.get("body", [])
                )
    retained = json.loads(
        subprocess.run(
            ["restic", "snapshots", "--json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert {snapshot["id"] for snapshot in retained} == {
        ids["recent-pending"],
        ids["old-canonical"],
    }
