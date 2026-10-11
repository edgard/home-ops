#!/usr/bin/env python3
"""Install pinned, checksum-verified operator binaries in a user-owned directory."""
import argparse
import hashlib
import io
import os
from pathlib import Path
import platform
import re
import tarfile
import tempfile
import urllib.request
import zipfile

SECRETSPEC_VERSION = '0.21.1'
BWS_VERSION = '2.1.0'


def download(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def install(tool, target):
    system = {'Darwin': 'apple-darwin', 'Linux': 'unknown-linux-gnu'}.get(platform.system())
    machine = {'arm64': 'aarch64', 'aarch64': 'aarch64', 'x86_64': 'x86_64', 'AMD64': 'x86_64'}.get(platform.machine())
    if not system or not machine:
        raise RuntimeError('Supported platforms: macOS/Linux arm64 and x86_64')
    triple = f'{machine}-{system}'
    if tool == 'secretspec':
        base = f'https://github.com/cachix/secretspec/releases/download/v{SECRETSPEC_VERSION}'
        archive = f'secretspec-{triple}.tar.xz'
        checksum = archive + '.sha256'
    else:
        base = f'https://github.com/bitwarden/sdk-sm/releases/download/bws-v{BWS_VERSION}'
        archive = f'bws-{triple}-{BWS_VERSION}.zip'
        checksum = f'bws-sha256-checksums-{BWS_VERSION}.txt'
    content = download(f'{base}/{archive}')
    lines = download(f'{base}/{checksum}').decode().splitlines()
    matches = [line.split()[0] for line in lines if line.split() and (len(lines) == 1 or line.split()[-1].lstrip('*') == archive)]
    if len(matches) != 1 or not re.fullmatch('[a-fA-F0-9]{64}', matches[0]) or hashlib.sha256(content).hexdigest() != matches[0].lower():
        raise RuntimeError(f'{tool} checksum verification failed')
    if archive.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            names = [name for name in bundle.namelist() if Path(name).name == tool]
            if len(names) != 1:
                raise RuntimeError('Unexpected binary archive layout')
            binary = bundle.read(names[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(content), mode='r:xz') as bundle:
            members = [member for member in bundle.getmembers() if member.isfile() and Path(member.name).name == tool]
            if len(members) != 1:
                raise RuntimeError('Unexpected binary archive layout')
            binary = bundle.extractfile(members[0]).read()
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target, delete=False) as output:
        temp_path = Path(output.name)
        output.write(binary)
    try:
        temp_path.chmod(0o755)
        os.replace(temp_path, target / tool)
    finally:
        temp_path.unlink(missing_ok=True)
    print(f'Installed {tool} in {target}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--only', choices=['secretspec', 'bws'])
    args = parser.parse_args()
    for name in ([args.only] if args.only else ['secretspec', 'bws']):
        install(name, args.directory)
