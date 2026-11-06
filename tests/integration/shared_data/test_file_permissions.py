"""Exercise the actual scheduled Pod capability set on a native Linux volume."""

import json
import subprocess
import uuid

import yaml

from tests.support.runtime import ROOT


def test_capture_and_restore_preserve_private_numeric_ownership_and_setgid(
    operations_image,
):
    volume = "home-ops-file-metadata-" + uuid.uuid4().hex
    subprocess.run(
        [
            "docker",
            "volume",
            "create",
            "--label",
            "home-ops-test=file-metadata",
            volume,
        ],
        capture_output=True,
        check=True,
    )
    files = ROOT / "ansible/roles/shared_data/files"
    base = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "-v",
        volume + ":/work",
        "-v",
        str(files) + ":/adapters:ro",
    ]
    capabilities = yaml.safe_load(
        (ROOT / "apps/selfhosted/shared-data/values.yaml").read_text()
    )["controllers"]["main"]["containers"]["operations"]["securityContext"][
        "capabilities"
    ]["add"]
    limited = [*base, "--cap-drop", "ALL"]
    for capability in capabilities:
        limited += ["--cap-add", capability]

    def run(command, *, restricted=False):
        result = subprocess.run(
            [*(limited if restricted else base), operations_image, "-c", command],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    copy = "import sys;sys.path.insert(0,'/adapters');from capture import copy_files;"
    try:
        run(
            "from pathlib import Path;import os;p=Path('/work/source/selfhosted/demo');p.mkdir(parents=True);(p/'file').write_text('original');os.chown(p/'file',1234,2345);os.chmod(p/'file',0o600);os.chown(p,1234,2345);os.chmod(p,0o2700)"
        )
        run(
            copy + "copy_files('/work/source','/work/stage',['selfhosted/demo'])",
            restricted=True,
        )
        run(
            "from pathlib import Path;Path('/work/source/selfhosted/demo/file').write_text('modified')"
        )
        run(
            copy
            + "copy_files('/work/source','/work/stage',['selfhosted/demo'],checksum=True)",
            restricted=True,
        )
        run(
            "from pathlib import Path;import os;p=Path('/work/live/selfhosted/demo');p.mkdir(parents=True);(p/'file').write_text('obsolete');os.chown(p/'file',4321,4321);os.chmod(p/'file',0o400);os.chown(p,4321,4321);os.chmod(p,0o700)"
        )
        run(
            copy
            + "copy_files('/work/stage','/work/live',['selfhosted/demo'],checksum=True)",
            restricted=True,
        )
        result = json.loads(
            run(
                "from pathlib import Path;import json;p=Path('/work/live/selfhosted/demo');s=p.stat();f=(p/'file').stat();print(json.dumps([s.st_uid,s.st_gid,s.st_mode&4095,f.st_uid,f.st_gid,f.st_mode&4095,(p/'file').read_text()]))"
            )
        )
        assert result == [1234, 2345, 0o2700, 1234, 2345, 0o600, "modified"]
    finally:
        subprocess.run(
            ["docker", "volume", "rm", volume], capture_output=True, check=True
        )
