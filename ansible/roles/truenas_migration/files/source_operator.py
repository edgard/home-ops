"""Private operator evidence, TrueNAS transport and cold macOS range capture."""

import contextlib
import fcntl
import hashlib
import json
import math
import os
import plistlib
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def config(path):
    path = Path(path)
    require(
        path.is_absolute() and not path.is_symlink(),
        "use an absolute private config path",
    )
    path = path.resolve(strict=True)
    require(
        not path.is_relative_to(Path(__file__).resolve().parents[4]),
        "keep migration evidence outside the repository",
    )
    for item in (path, path.parent):
        st = item.stat()
        require(
            st.st_uid == os.geteuid() and st.st_mode & 0o077 == 0,
            "operator config or directory is not private",
        )
    c = json.loads(path.read_text())
    settings = {
        "source_host": r"(?:[a-zA-Z0-9_][a-zA-Z0-9_.-]*@)?[a-zA-Z0-9][a-zA-Z0-9.-]*",
        "source_dataset": r"[a-zA-Z0-9][a-zA-Z0-9_.-]*/[a-zA-Z0-9][a-zA-Z0-9_.-]*",
        "recovery_dataset": r"[a-zA-Z0-9][a-zA-Z0-9_.-]*/[a-zA-Z0-9][a-zA-Z0-9_.-]*",
        "snapshot": r"[a-zA-Z0-9][a-zA-Z0-9_.-]*",
        "vm": r"[a-zA-Z0-9][a-zA-Z0-9_.-]*",
        "ssd_by_id": r"/dev/disk/by-id/[a-zA-Z0-9][a-zA-Z0-9_+.:-]*",
        "spool_partuuid": r"[a-f0-9-]{36}",
        "spool_guid": r"[1-9][0-9]{0,19}",
        "boot_guid": r"[1-9][0-9]{0,19}",
        "data_guid": r"[1-9][0-9]{0,19}",
    }
    require(
        c.keys() - {"hold_datasets"} == settings.keys(),
        "review required fields in migration runbook",
    )
    for name, pattern in settings.items():
        require(
            isinstance(c[name], str) and re.fullmatch(pattern, c[name]),
            "invalid field: " + name,
        )
    require(
        str(uuid.UUID(c["spool_partuuid"])) == c["spool_partuuid"],
        "invalid partition GUID",
    )
    require(
        len({c["boot_guid"], c["spool_guid"], c["data_guid"]}) == 3,
        "pool GUIDs must differ",
    )
    extra = c.setdefault("hold_datasets", [])
    require(
        isinstance(extra, list)
        and all(
            isinstance(name, str)
            and re.fullmatch(settings["source_dataset"], name)
            and name.split("/")[0] == c["recovery_dataset"].split("/")[0]
            and name != c["recovery_dataset"]
            for name in extra
        ),
        "invalid list of surviving data sets to hold",
    )
    c["session"] = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
    return c, path.parent


def receipt(directory, c, action):
    result = json.loads((directory / (action + ".json")).read_text())
    require(
        result["session"] == c["session"], "evidence belongs to another configuration"
    )
    return result


def record(directory, c, action, report):
    data = dict(report, session=c["session"])
    data.pop("created", None)
    dest = directory / (action + ".json")
    if dest.exists():
        old = receipt(directory, c, action)
        # Preflight capacity is a point-in-time measurement.
        require(
            old["geometry"] == data["geometry"]
            and (action == "preflight" or old == data),
            "existing evidence conflicts with this operation",
        )
        return
    with tempfile.NamedTemporaryFile(dir=directory, mode="w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
        os.link(f.name, dest)


def truenas(c, action):
    # All values in this payload are nonsecret identifiers. OpenSSH forwards
    # its command as a shell string, so quote every remote argument.
    command = shlex.join(["sudo", "-n", "python3", "-", action, json.dumps(c)])
    args = [
        "ssh",
        "-T",
        "-oBatchMode=yes",
        "-oStrictHostKeyChecking=yes",
        "-oUpdateHostKeys=no",
        "-oConnectTimeout=10",
        c["source_host"],
        command,
    ]
    with Path(__file__).with_name("source.py").open("rb") as script:
        return json.loads(subprocess.check_output(args, stdin=script))


def mac_diskinfo(disk):
    return plistlib.loads(subprocess.check_output(["diskutil", "info", "-plist", disk]))


def dd_args(raw, start, count):
    block = math.gcd(start, count, 1024 * 1024)
    args = [
        "/bin/dd",
        "if=" + raw,
        f"bs={block}",
        f"skip={start // block}",
        f"count={count // block}",
    ]
    return args if os.access(raw, os.R_OK) else ["sudo", "-n", *args]


def read_region(raw, start, count):
    value = subprocess.check_output(
        dd_args(raw, start, count), stderr=subprocess.DEVNULL
    )
    require(len(value) == count, "short device read")
    return value


def check_gpt(raw, g):
    sector, size = g["sector_bytes"], g["disk_bytes"]
    last = size // sector - 1
    for lba, mirror in ((1, last), (last, 1)):
        header = read_region(raw, lba * sector, sector)
        require(header[:8] == b"EFI PART", "missing GPT header")
        length, crc = struct.unpack_from("<II", header, 12)
        require(92 <= length <= sector, "invalid GPT header length")
        require(
            zlib.crc32(header[:16] + bytes(4) + header[20:length]) == crc,
            "invalid GPT header checksum",
        )
        require(
            struct.unpack_from("<QQ", header, 24) == (lba, mirror),
            "GPT disk geometry mismatch",
        )
        require(
            str(uuid.UUID(bytes_le=header[56:72])) == g["gpt_guid"],
            "SSD disk GUID mismatch",
        )
        entry_lba, entries, width, checksum = struct.unpack_from("<QIII", header, 72)
        require(
            width >= 128 and width % 8 == 0 and 0 < entries * width <= 1024 * 1024,
            "invalid GPT table size",
        )
        area = math.ceil(entries * width / sector) * sector
        start = entry_lba * sector
        require(
            (lba == 1 and sector * 2 <= start and start + area <= g["prefix_bytes"])
            or (
                lba == last
                and start >= size - g["tail_bytes"]
                and start + area <= last * sector
            ),
            "partition table exceeds expected GPT backup regions",
        )
        table = read_region(raw, start, area)[: entries * width]
        require(zlib.crc32(table) == checksum, "invalid partition table checksum")
        parts = []
        for pos in range(0, len(table), width):
            row = table[pos : pos + width]
            if row[:16] != bytes(16):
                first, end = struct.unpack_from("<QQ", row, 32)
                parts.append(
                    (first, end + 1 - first, str(uuid.UUID(bytes_le=row[16:32])))
                )
        require(
            sorted(parts)
            == list(
                zip(g["partition_starts"], g["partition_sectors"], g["partition_guids"])
            ),
            "SSD partitions do not match the TrueNAS preflight",
        )


def capture(directory, name, raw, start, count):
    dest = directory / name
    if dest.is_symlink():
        raise ValueError("recovery artifact must be a regular file")
    created = not dest.exists()
    with contextlib.ExitStack() as stack:
        target = (
            stack.enter_context(tempfile.NamedTemporaryFile(dir=directory))
            if created
            else None
        )
        process = stack.enter_context(
            subprocess.Popen(
                dd_args(raw, start, count),
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        )
        digest = hashlib.sha256()
        total = 0
        while chunk := process.stdout.read(8 << 20):
            total += len(chunk)
            digest.update(chunk)
            if target:
                target.write(chunk)
        require(process.wait() == 0 and total == count, "incomplete offline disk read")
        if target:
            target.flush()
            os.fsync(target.fileno())
        with open(target.name if target else dest, "rb") as f:
            require(
                hashlib.file_digest(f, "sha256").digest() == digest.digest(),
                "recovery file checksum mismatch",
            )
        if target:
            os.link(target.name, dest)
    return {
        "file": name,
        "offset": start,
        "bytes": count,
        "sha256": digest.hexdigest(),
    }, created


def mac_capture(directory, g):
    disk = os.environ.get("MIGRATION_MAC_DISK", "")
    require(
        sys.platform == "darwin" and re.fullmatch(r"/dev/disk[0-9]+", disk),
        "select an external whole Mac disk",
    )
    info = mac_diskinfo(disk)
    require(
        info.get("WholeDisk", info.get("Whole")) is True
        and info.get("Internal") is False
        and info.get("VirtualOrPhysical") == "Physical",
        "selected device is not an external physical whole disk",
    )
    require(
        info["DeviceBlockSize"] == g["sector_bytes"]
        and info["TotalSize"] == g["disk_bytes"],
        "enclosure logical sector size or SSD size differs from preflight",
    )
    layout = plistlib.loads(
        subprocess.check_output(["diskutil", "list", "-plist", disk])
    )
    for part in layout["AllDisksAndPartitions"][0]["Partitions"]:
        require(
            not mac_diskinfo(part["DeviceIdentifier"]).get("MountPoint"),
            "unmount all SSD partitions on the Mac",
        )
    raw = "/dev/r" + info["DeviceIdentifier"]
    check_gpt(raw, g)
    items = [
        ("boot-prefix.raw", 0, g["prefix_bytes"]),
        ("backup-gpt.raw", g["disk_bytes"] - g["tail_bytes"], g["tail_bytes"]),
    ]
    needed = sum(n for name, _, n in items if not (directory / name).exists())
    require(
        shutil.disk_usage(directory).free > needed,
        "insufficient local recovery storage",
    )
    records = [
        capture(directory, name, raw, offset, count) for name, offset, count in items
    ]
    check_gpt(raw, g)
    return {
        "geometry": g,
        "ranges": [r for r, _ in records],
        "created": any(done for _, done in records),
    }


def main():
    action, filename = sys.argv[1:]
    require(
        action in ("preflight", "stage", "archive", "boot-backup"),
        "unknown migration action",
    )
    require(
        action == "preflight" or os.environ.get("MIGRATION_CONFIRM") == action,
        "set MIGRATION_CONFIRM to the requested operation name",
    )
    os.umask(0o077)
    c, directory = config(filename)
    with (directory / ".migration.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if action != "preflight":
            c["expected_geometry"] = receipt(directory, c, "preflight")["geometry"]
        if action == "archive":
            c["snapshot_guid"] = receipt(directory, c, "stage")["snapshot_guid"]
        if action == "boot-backup":
            previous = receipt(directory, c, "archive")
            require(
                previous["geometry"] == c["expected_geometry"]
                and previous["bytes"] == previous["geometry"]["partition_bytes"],
                "source partition recovery receipt does not match preflight",
            )
            report = mac_capture(directory, previous["geometry"])
        else:
            report = truenas(c, action)
        record(directory, c, action, report)
        print("created" if report["created"] else "verified")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(f"migration operation failed (exit {error.returncode})")
    except (KeyError, OSError, ValueError) as error:
        sys.exit(str(error))
