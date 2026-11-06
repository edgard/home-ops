"""Initialize an isolated Redis recovery emptyDir from exact captured RDB bytes."""

import argparse
import hashlib
import os
import re
import shutil
from pathlib import Path


def prepare(source, destination, expected_sha256, password_file):
    source, destination = Path(source), Path(destination)
    if not re.fullmatch("[a-f0-9]{64}", expected_sha256):
        raise ValueError("captured RDB SHA256 required")
    if source.is_symlink() or not source.is_file():
        raise ValueError("captured regular RDB required")
    if (
        destination.is_symlink()
        or not destination.is_dir()
        or any(destination.iterdir())
    ):
        raise ValueError("fresh isolated recovery emptyDir required")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        header = stream.read(9)
        if not re.fullmatch(b"REDIS[0-9]{4}", header):
            raise ValueError("Redis RDB header missing")
        digest.update(header)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("captured RDB checksum mismatch")
    password = Path(password_file).read_text().strip()
    if len(password) < 32:
        raise ValueError("private recovery password required")
    target = destination / "dump.rdb"
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    # Readback prevents a changed source between hash and copy becoming loadable.
    copied = hashlib.sha256()
    with target.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            copied.update(block)
    if copied.hexdigest() != expected_sha256:
        raise ValueError("copied RDB checksum mismatch")
    acl = destination / "recovery.acl"
    with acl.open("x") as stream:
        stream.write(
            "user default on #"
            + hashlib.sha256(password.encode()).hexdigest()
            + " ~* &* -@all +ping +info +select +scan +dump +pexpiretime +exists\n"
        )
        stream.flush()
        os.fsync(stream.fileno())
    for path in [target, acl]:
        path.chmod(0o600)
        os.chown(path, 999, 999)
    destination.chmod(0o700)
    os.chown(destination, 999, 999)
    descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--password-file", required=True)
    args = parser.parse_args()
    prepare(args.source, args.destination, args.sha256, args.password_file)


if __name__ == "__main__":
    main()
