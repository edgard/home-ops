"""Run through SSH on TrueNAS. Only archive reads a raw device."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(*argv):
    return subprocess.check_output(argv, text=True).strip()


def middleware(method):
    return json.loads(run("midclt", "call", method))


def prop(name, key):
    return run("zfs", "get", "-Hp", "-o", "value", key, name)


def exists(dataset):
    return (
        dataset
        in run("zfs", "list", "-H", "-o", "name", "-t", "filesystem").splitlines()
    )


def vdevs(pool):
    paths = []
    for line in run("zpool", "status", "-LP", pool).splitlines():
        fields = line.split()
        if fields and fields[0].startswith("/dev/"):
            require(fields[1] == "ONLINE", "unhealthy pool member")
            paths.append(Path(fields[0]).resolve())
    require(paths, "pool has no identifiable physical members")
    return paths


def disk_geometry(c):
    disk = Path(c["ssd_by_id"]).resolve(strict=True)
    require(run("lsblk", "-dnro", "TYPE", str(disk)) == "disk", "expected a whole SSD")
    table = json.loads(run("sfdisk", "--json", str(disk)))["partitiontable"]
    sector = int(table["sectorsize"])
    size = int(run("blockdev", "--getsize64", str(disk)))
    require(
        table["label"] == "gpt" and table["unit"] == "sectors",
        "expected GPT in sectors",
    )
    require(size % sector == 0 and sector in (512, 4096), "unexpected sector geometry")
    parts = sorted(table["partitions"], key=lambda part: int(part["start"]))
    last = parts[-1]
    partition = Path("/dev/disk/by-partuuid", c["spool_partuuid"]).resolve(strict=True)
    require(
        last["uuid"].lower() == c["spool_partuuid"]
        and Path(last["node"]).resolve() == partition,
        "source pool partition must be the final partition of this SSD",
    )
    prefix = int(last["start"]) * sector
    payload = int(last["size"]) * sector
    require(size - prefix - payload > 0, "missing secondary GPT range")
    require(
        run("blockdev", "--getsize64", str(partition)) == str(payload),
        "partition size mismatch",
    )
    return (
        {
            "gpt_guid": table["id"].lower(),
            "partition_guids": [p["uuid"].lower() for p in parts],
            "partition_starts": [int(p["start"]) for p in parts],
            "partition_sectors": [int(p["size"]) for p in parts],
            "sector_bytes": sector,
            "disk_bytes": size,
            "prefix_bytes": prefix,
            "partition_bytes": payload,
            "tail_bytes": size - prefix - payload,
        },
        disk,
        partition,
    )


def mounts(dataset):
    path = Path(prop(dataset, "mountpoint"))
    require(path.is_absolute(), "expected an absolute mounted dataset")
    require(
        run("findmnt", "-nro", "SOURCE,FSTYPE", "-T", str(path)).split()
        == [dataset, "zfs"],
        "dataset is not the mounted filesystem at its declared path",
    )
    return path


def source_state(c, archived):
    geometry, disk, partition = disk_geometry(c)
    pools = {
        row.split("\t")[0]: row.split("\t")[1]
        for row in run("zpool", "list", "-Hp", "-o", "name,guid").splitlines()
    }
    source_pool = c["source_dataset"].split("/")[0]
    data_pool = c["recovery_dataset"].split("/")[0]
    boot_pool = next(
        (name for name, guid in pools.items() if guid == c["boot_guid"]), None
    )
    require(
        boot_pool and pools.get(data_pool) == c["data_guid"],
        "boot or surviving pool identity changed",
    )
    require(
        source_pool != data_pool and boot_pool not in (source_pool, data_pool),
        "pool roles overlap",
    )
    members = vdevs(boot_pool)
    require(
        len(members) == 1
        and run("lsblk", "-nro", "PKNAME", str(members[0])) == disk.name,
        "boot pool is not on the selected SSD",
    )
    require(members[0] != partition, "boot partition overlaps the recovery partition")
    require(
        run("zpool", "list", "-H", "-o", "health", data_pool) == "ONLINE",
        "surviving pool is unhealthy",
    )
    for dev in vdevs(data_pool):
        require(
            dev != disk and run("lsblk", "-dnro", "PKNAME", str(dev)) != disk.name,
            "surviving pool has a vdev on the disk being flashed",
        )
    if archived:
        require(
            source_pool not in pools and c["spool_guid"] not in pools.values(),
            "export source pool first",
        )
        labels = run("zdb", "-l", str(partition))
        require(
            f"pool_guid: {c['spool_guid']}"
            in {line.strip() for line in labels.splitlines()},
            "exported partition has unexpected ZFS pool GUID",
        )
    else:
        require(
            pools.get(source_pool) == c["spool_guid"]
            and vdevs(source_pool) == [partition],
            "source pool is not the single expected SSD partition",
        )
        mounts(c["source_dataset"])
        require(
            run("zfs", "list", "-H", "-r", "-o", "name", c["source_dataset"])
            == c["source_dataset"],
            "nested appdata datasets need a recursive copy plan",
        )
    return geometry, partition


def check_writers(c):
    vms = middleware("vm.query")
    vm = next((vm for vm in vms if vm["name"] == c["vm"]), None)
    require(
        vm and vm["status"]["state"] == "STOPPED" and not vm["autostart"],
        "stop VM and disable autostart",
    )
    for service in middleware("service.query"):
        if service["service"] in ("nfs", "cifs"):
            require(
                service["state"] == "STOPPED" and not service["enable"],
                "stop shares and disable autostart",
            )
    data_root = mounts(c["recovery_dataset"].split("/")[0])
    for job in middleware("cloudsync.query"):
        path = Path(job["path"])
        if data_root == path or data_root in path.parents:
            require(
                not job["enabled"]
                and (job.get("job") or {}).get("state") not in ("RUNNING", "WAITING"),
                "suspend and finish cloud sync before cutover",
            )


def recovery_root(c, create=False):
    name = c["recovery_dataset"]
    parent, leaf = name.split("/")
    path = mounts(parent) / leaf
    for method in ("sharing.nfs.query", "sharing.smb.query"):
        for share in middleware(method):
            share_path = Path(share["path"]).resolve()
            require(
                share_path != path
                and share_path not in path.parents
                and path not in share_path.parents,
                "recovery dataset overlaps a configured share",
            )
    if not exists(name):
        require(
            create and not path.exists(),
            "recovery target missing or would mask an existing directory",
        )
        run(
            "zfs",
            "create",
            "-o",
            "acltype=posix",
            "-o",
            "sharenfs=off",
            "-o",
            "sharesmb=off",
            "-o",
            "home-ops:migration=" + c["session"],
            name,
        )
    require(
        prop(name, "home-ops:migration") == c["session"] and mounts(name) == path,
        "recovery target is not owned by this operation",
    )
    require(
        prop(name, "sharesmb") == "off" and prop(name, "sharenfs") == "off",
        "unexpected ZFS share",
    )
    if path.stat().st_mode & 0o7777 != 0o700:
        path.chmod(0o700)
    return path


def hold_snapshot(c, source):
    source_snap = source + "@" + c["snapshot"]
    snapshots = run(
        "zfs", "list", "-Hr", "-t", "snapshot", "-o", "name", source
    ).splitlines()
    if source_snap not in snapshots:
        run("zfs", "snapshot", "-o", "home-ops:migration=" + c["session"], source_snap)
    require(
        prop(source_snap, "home-ops:migration") == c["session"],
        "snapshot name was already in use",
    )
    hold(source_snap)
    return prop(source_snap, "guid")


def hold(snapshot):
    held = [
        line.split("\t")[1] for line in run("zfs", "holds", "-H", snapshot).splitlines()
    ]
    if "home-ops-cutover" not in held:
        run("zfs", "hold", "home-ops-cutover", snapshot)


def acl_inventory(dataset, directory):
    """Use the TrueNAS ACL reader on every file and directory, without following links."""
    report = {
        "acltype": prop(dataset, "acltype"),
        "checked": 0,
        "nontrivial": 0,
        "examples": [],
    }
    if report["acltype"].lower() != "nfsv4":
        return report

    def inspect(paths):
        output = subprocess.check_output(["nfs4xdr_getfacl", "-jn", *paths])
        rows = output.splitlines()
        require(len(rows) == len(paths), "incomplete NFSv4 ACL inventory")
        for row, path in zip(rows, paths):
            acl = json.loads(row)
            require(
                acl["path"] == str(path) and type(acl["trivial"]) is bool,
                "unexpected NFSv4 ACL reader output",
            )
            report["checked"] += 1
            if not acl["trivial"]:
                report["nontrivial"] += 1
                if len(report["examples"]) < 20:
                    report["examples"].append(str(path.relative_to(directory)))

    def walk_error(error):
        raise error

    batch = [directory]
    for root, folders, files in os.walk(directory, onerror=walk_error):
        # Snapshot control directories can be visible at the dataset root.
        if Path(root) == directory and ".zfs" in folders:
            folders.remove(".zfs")
        for name in folders + files:
            path = Path(root, name)
            if path.is_symlink():
                continue
            batch.append(path)
            if len(batch) == 64:
                inspect(batch)
                batch.clear()
    if batch:
        inspect(batch)
    return report


def stage(c):
    source = c["source_dataset"]
    target = c["recovery_dataset"] + "/appdata"
    source_snap = source + "@" + c["snapshot"]
    target_snap = target + "@" + c["snapshot"]
    for dataset in c["hold_datasets"]:
        require(exists(dataset), "configured dataset to hold is missing")
    recovery_root(c, create=True)
    holds = {name: hold_snapshot(c, name) for name in [source, *c["hold_datasets"]]}
    guid = holds[source]
    # An inherited ACL type can change when receiving into a private staging parent.
    acl_options = []
    for key in ("acltype", "aclmode", "aclinherit", "xattr"):
        acl_options.extend(["-o", key + "=" + prop(source, key)])
    created = not exists(target)
    if created:
        with subprocess.Popen(
            ["zfs", "send", "-p", source_snap], stdout=subprocess.PIPE
        ) as sender:
            try:
                subprocess.run(
                    [
                        "zfs",
                        "receive",
                        "-u",
                        "-x",
                        "mountpoint",
                        "-o",
                        "readonly=on",
                        "-o",
                        "canmount=on",
                        "-o",
                        "sharenfs=off",
                        "-o",
                        "sharesmb=off",
                        *acl_options,
                        target,
                    ],
                    stdin=sender.stdout,
                    check=True,
                )
            finally:
                sender.stdout.close()
            require(sender.wait() == 0, "snapshot send did not complete")
    require(
        prop(target_snap, "guid") == guid and prop(target, "readonly") == "on",
        "destination snapshot or read-only policy mismatch",
    )
    expected_path = mounts(c["recovery_dataset"]) / "appdata"
    require(
        prop(target, "mountpoint") == str(expected_path),
        "staged dataset has an unexpected mountpoint",
    )
    for key in (
        "acltype",
        "aclmode",
        "aclinherit",
        "xattr",
        "casesensitivity",
        "normalization",
    ):
        require(
            prop(source, key) == prop(target, key),
            "staged dataset property differs: " + key,
        )
    hold(target_snap)
    if prop(target, "mounted") == "no":
        require(
            not expected_path.exists()
            or (
                expected_path.is_dir()
                and not expected_path.is_symlink()
                and not any(expected_path.iterdir())
            ),
            "mount would mask existing staging data",
        )
        run("zfs", "mount", target)
    require(mounts(target) == expected_path, "staging mount is missing")
    return {
        "created": created,
        "snapshot_guid": guid,
        "staged_dataset": target,
        "pool_guid": c["data_guid"],
        "held_snapshot_guids": holds,
        "acl_inventory": {
            name: acl_inventory(
                name, mounts(name) / ".zfs" / "snapshot" / c["snapshot"]
            )
            for name in holds
        },
    }


def archive(c, geometry, partition):
    directory = recovery_root(c)
    archive_file = directory / "spool.partition.raw"
    size = geometry["partition_bytes"]
    if archive_file.exists():
        require(
            archive_file.is_file()
            and not archive_file.is_symlink()
            and archive_file.stat().st_size == size,
            "existing archive has wrong type or size",
        )
        with archive_file.open("rb") as backup, partition.open("rb") as source:
            digest = hashlib.file_digest(backup, "sha256").hexdigest()
            require(
                hashlib.file_digest(source, "sha256").hexdigest() == digest,
                "existing archive differs",
            )
        return {"created": False, "bytes": size, "sha256": digest}
    require(
        shutil.disk_usage(directory).free > size,
        "not enough space for a complete partition image",
    )
    fd, tmp = tempfile.mkstemp(prefix=".partition-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as backup, partition.open("rb") as source:
            digest = hashlib.sha256()
            while chunk := source.read(8 << 20):
                backup.write(chunk)
                digest.update(chunk)
            backup.flush()
            os.fsync(backup.fileno())
        require(os.stat(tmp).st_size == size, "incomplete partition read")
        with open(tmp, "rb") as copied:
            require(
                hashlib.file_digest(copied, "sha256").digest() == digest.digest(),
                "archive readback failed",
            )
        source_state(c, archived=True)
        os.link(tmp, archive_file)
    finally:
        os.unlink(tmp)
    return {"created": True, "bytes": size, "sha256": digest.hexdigest()}


def main():
    action, raw_config = sys.argv[1:]
    c = json.loads(raw_config)
    os.umask(0o077)
    geometry, partition = source_state(c, archived=action == "archive")
    report = {"geometry": geometry, "created": False}
    if action == "preflight":
        data_pool = c["recovery_dataset"].split("/")[0]
        report.update(
            source_pool_guid=c["spool_guid"],
            data_pool_guid=c["data_guid"],
            source_referenced_bytes=int(prop(c["source_dataset"], "referenced")),
            data_available_bytes=int(prop(data_pool, "available")),
            data_altroot=run("zpool", "get", "-H", "-o", "value", "altroot", data_pool),
            source_properties=run(
                "zfs",
                "get",
                "-Hp",
                "-o",
                "name,property,value,source",
                "acltype,aclmode,aclinherit,xattr,casesensitivity,normalization",
                c["source_dataset"],
            ).splitlines(),
            data_properties=run(
                "zfs",
                "get",
                "-Hpr",
                "-t",
                "filesystem",
                "-o",
                "name,property,value,source",
                "mountpoint,canmount,sharenfs,sharesmb,readonly",
                data_pool,
            ).splitlines(),
        )
    else:
        require(
            geometry == c["expected_geometry"], "SSD layout changed after preflight"
        )
        check_writers(c)
        if action == "stage":
            report.update(stage(c))
        elif action == "archive":
            require(
                prop(c["recovery_dataset"] + "/appdata@" + c["snapshot"], "guid")
                == c["snapshot_guid"],
                "staged snapshot identity changed",
            )
            report.update(archive(c, geometry, partition))
        else:
            raise ValueError("unsupported source operation")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
