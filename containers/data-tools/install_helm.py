"""Install the architecture-matched official Helm archive after a pinned SHA check."""

import hashlib
import io
import os
import platform
import tarfile
import urllib.request
from pathlib import Path

VERSION = "v4.3.1"
PINS = {
    "x86_64": (
        "amd64",
        "0403a88ae20913d11b10a2467b50087721fea7581736da6b9d3992f5357fe54b",
    ),
    "aarch64": (
        "arm64",
        "8cf8f66ecbc252ac8f7f06cca68aba88508ddfde3a6a34feb1678ad1694b4f88",
    ),
}


def main():
    arch, expected = PINS[platform.machine()]
    url = f"https://get.helm.sh/helm-{VERSION}-linux-{arch}.tar.gz"
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = response.read(40 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Helm archive checksum differs from official pinned release")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        member = archive.getmember(f"linux-{arch}/helm")
        if not member.isfile() or member.size > 200 * 1024 * 1024:
            raise ValueError("unexpected Helm executable")
        destination = Path("/usr/local/bin/helm")
        destination.write_bytes(archive.extractfile(member).read())
        os.chmod(destination, 0o755)


if __name__ == "__main__":
    main()
