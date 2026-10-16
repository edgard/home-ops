import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from tests.support.runtime import ROOT, environment, executable
from tests.support.sources import read_yaml


@pytest.mark.parametrize("failure", [None, "checksum", "version"])
def test_ci_secretspec_installation_preserves_binary_on_failure(tmp_path, failure):
    # Exercise the actual action shell, replacing only the network boundary.
    steps = read_yaml(ROOT / ".github/actions/setup-toolchain/action.yml")["runs"]["steps"]
    (step,) = [step for step in steps if "secretspec-x86_64" in step.get("run", "")]
    defaults = tmp_path / "ansible/roles/cli_secrets/defaults/main.yml"
    defaults.parent.mkdir(parents=True)
    defaults.write_text("---\ncli_secrets_secretspec_version: '9.8.7' # fixture pin\n")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    name = "secretspec-x86_64-unknown-linux-gnu"
    archive = downloads / (name + ".tar.xz")
    content = b'#!/bin/sh\nprintf "%s\\n" "secretspec 9.8.7"\n'
    if failure == "version":
        content = content.replace(b"9.8.7", b"0.0.1")
    with tarfile.open(archive, "w:xz") as package:
        member = tarfile.TarInfo(name + "/secretspec")
        member.size, member.mode = len(content), 0o755
        package.addfile(member, io.BytesIO(content))
    digest = "0" * 64 if failure == "checksum" else hashlib.sha256(archive.read_bytes()).hexdigest()
    (downloads / (archive.name + ".sha256")).write_text(digest + "  " + archive.name + "\n")
    record = tmp_path / "requests.json"
    record.write_text("[]")
    (tmp_path / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    executable(
        tmp_path,
        "curl",
        "import json,os,pathlib,shutil,sys\n"
        "args=sys.argv[1:];url=args[-1]\n"
        "base='https://github.com/cachix/secretspec/releases/download/v9.8.7/'\n"
        "assert url.startswith(base),url\n"
        "name=url.removeprefix(base)\n"
        "assert name in ['secretspec-x86_64-unknown-linux-gnu.tar.xz','secretspec-x86_64-unknown-linux-gnu.tar.xz.sha256']\n"
        "record=pathlib.Path(os.environ['FIXTURE_RECORD'])\n"
        "requests=json.loads(record.read_text()) if record.exists() else []\n"
        "destination=args[args.index('-fsSLo')+1]\n"
        "record.write_text(json.dumps(requests+[{'url':url,'destination':destination}]))\n"
        "shutil.copyfile(pathlib.Path(os.environ['FIXTURE_DOWNLOADS'])/name,destination)\n",
    )
    runner = tmp_path / "runner"
    binary = runner / "home-ops-bin/secretspec"
    binary.parent.mkdir(parents=True)
    original = b"previous executable\n"
    binary.write_bytes(original)
    github_path = tmp_path / "github-path"
    github_path.write_text("")
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env=environment(tmp_path, {
            "RUNNER_TEMP": str(runner), "GITHUB_PATH": str(github_path),
            "FIXTURE_DOWNLOADS": str(downloads),
            "FIXTURE_RECORD": str(record),
        }),
        capture_output=True, text=True, timeout=30,
    )
    assert (result.returncode == 0) == (failure is None), result.stdout + result.stderr
    requests = json.loads(record.read_text())
    assert len(requests) == 2
    for request in requests:
        stage = Path(request["destination"]).parent
        assert stage.parent == runner, "Stage downloads inside the runner's temporary directory"
        assert not stage.exists(), "Installer must clean staged downloads on every exit"
    if failure:
        assert binary.read_bytes() == original
        assert not github_path.read_text(), "Do not register a failed installation"
    else:
        assert binary.read_bytes() == content
        assert binary.stat().st_mode & 0o777 == 0o755
        assert github_path.read_text().splitlines() == [str(binary.parent)]
