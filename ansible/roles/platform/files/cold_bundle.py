"""Whitelisted committed public build/source bundles; no Kubernetes I/O.

The CLI reads a Git commit, never the worktree/index or ignored operator files.
Extraction accepts only checksum-bound regular YAML assets and private directories.
"""

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path, PurePosixPath

MAX_RAW = 32 * 1024 * 1024
MAX_BUNDLE = 700 * 1024
META = ".home-ops-source.json"
IMAGE_META = ".home-ops-build.json"
PLAYBOOKS = {
    "ansible/playbooks/shared-data.yml",
    "ansible/playbooks/platform-recovery-executor.yml",
}
CONTAINER_FILES = {
    "Dockerfile",
    "ansible.cfg",
    "hosts.yml",
    "requirements.txt",
    "install_helm.py",
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def safe_name(name):
    path = PurePosixPath(name)
    return (
        bool(name)
        and not path.is_absolute()
        and ".." not in path.parts
        and str(path) == name
        and "\\" not in name
    )


def asset(name):
    parts = PurePosixPath(name).parts
    return (
        name == "ansible/roles/shared_data/files/registry.yaml"
        or (
            len(parts) == 4
            and parts[0] == "apps"
            and parts[3] in {"app.yaml", "values.yaml"}
        )
        or (
            len(parts) == 5
            and parts[0] == "apps"
            and parts[3] == "manifests"
            and parts[4].endswith((".yaml", ".yml"))
        )
        or (parts and parts[0] == "argocd" and name.endswith((".yaml", ".yml")))
    )


def code(name):
    if name == "ansible/roles/shared_data/files/registry.yaml":
        return False
    parts = PurePosixPath(name).parts
    return (
        name in PLAYBOOKS
        or name == "ansible/requirements.yml"
        or (
            len(parts) == 3
            and parts[:2] == ("containers", "data-tools")
            and parts[2] in CONTAINER_FILES
        )
        or (
            len(parts) >= 5
            and parts[:2] == ("ansible", "roles")
            and parts[2] in {"platform", "shared_data"}
            and parts[3]
            in {"defaults", "tasks", "filter_plugins", "templates", "files"}
            and name.endswith((".py", ".yml", ".yaml", ".j2"))
        )
    )


def context_file(name):
    return code(name) or name in {
        ".dockerignore",
        "ansible/requirements.yml",
        "ansible/roles/shared_data/files/registry.yaml",
    }


def inventory(files):
    return {name: sha(data) for name, data in sorted(files.items())}


def code_digest(files):
    return sha(
        canonical(inventory({name: data for name, data in files.items() if code(name)}))
    )


def committed(root, revision):
    if not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("an immutable source revision is required")
    result = subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            revision,
            "--",
            "apps",
            "argocd",
            "ansible/roles/platform",
            "ansible/roles/shared_data",
            "ansible/playbooks/shared-data.yml",
            "ansible/playbooks/platform-recovery-executor.yml",
            "ansible/requirements.yml",
            "containers/data-tools",
            ".dockerignore",
        ],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return regular_archive(result.stdout)


def regular_archive(raw):
    if len(raw) > MAX_RAW:
        raise ValueError("public archive exceeds its bounded size")
    files = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
        for member in archive:
            if member.isdir():
                continue
            if (
                not member.isfile()
                or not safe_name(member.name)
                or member.name in files
            ):
                raise ValueError("only unique regular safe public paths are accepted")
            total += member.size
            if total > MAX_RAW or member.size < 0:
                raise ValueError("public archive exceeds its bounded expanded size")
            files[member.name] = archive.extractfile(member).read(MAX_RAW + 1)
    return files


def archive(files, compressed=False):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in sorted(files.items()):
            if not safe_name(name):
                raise ValueError("unsafe public archive path")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    raw = out.getvalue()
    return gzip.compress(raw, mtime=0) if compressed else raw


def source_bundle(files, revision):
    import yaml

    selected = {name: data for name, data in files.items() if asset(name)}
    registry = yaml.safe_load(selected["ansible/roles/shared_data/files/registry.yaml"])
    source_sha = sha(canonical({"registry": registry, "revision": revision}))
    metadata = {
        "version": 1,
        "revision": revision,
        "source_sha256": source_sha,
        "files": inventory(selected),
    }
    raw = archive({**selected, META: canonical(metadata)}, compressed=True)
    if len(raw) > MAX_BUNDLE:
        raise ValueError("source bundle exceeds the single immutable ConfigMap limit")
    return {
        "revision": revision,
        "source_sha256": source_sha,
        "bundle_sha256": sha(raw),
        "code_sha256": code_digest(files),
        "bundle_base64": base64.b64encode(raw).decode(),
    }


def build_context(files, revision):
    selected = {name: data for name, data in files.items() if context_file(name)}
    metadata = {
        "version": 1,
        "revision": revision,
        "code_sha256": code_digest(selected),
        "files": inventory(
            {name: data for name, data in selected.items() if code(name)}
        ),
    }
    return archive({**selected, IMAGE_META: canonical(metadata)})


def image_provenance(root, revision):
    root = Path(root)
    expected = json.loads((root / IMAGE_META).read_text())
    if expected["revision"] != revision or not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("image build revision differs from committed build input")
    actual = {name: (root / name).read_bytes() for name in expected["files"]}
    if (
        any(not code(name) for name in actual)
        or inventory(actual) != expected["files"]
        or code_digest(actual) != expected["code_sha256"]
    ):
        raise ValueError("image runtime code differs from committed build input")
    result = {
        "version": 1,
        "image_revision": revision,
        "code_sha256": expected["code_sha256"],
        "files": expected["files"],
    }
    (root / ".image-provenance.json").write_bytes(canonical(result))
    return result


def verify_image(root, code_sha):
    root = Path(root)
    proof = json.loads((root / ".image-provenance.json").read_text())
    actual = {name: (root / name).read_bytes() for name in proof["files"]}
    if (
        any(not code(name) for name in actual)
        or inventory(actual) != proof["files"]
        or code_digest(actual) != code_sha
        or proof["code_sha256"] != code_sha
        or not re.fullmatch("[a-f0-9]{40}", proof["image_revision"])
    ):
        raise ValueError(
            "actual image runtime code is incompatible with requested clean source"
        )
    return proof


def unpack(raw, destination, revision, expected_sha, expected_source):
    import yaml

    if len(raw) > MAX_BUNDLE or sha(raw) != expected_sha:
        raise ValueError("source bundle checksum or compressed size differs")
    # Bound decompression before tar parsing, including gzip bombs.
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        expanded = stream.read(MAX_RAW + 1)
    files = regular_archive(expanded)
    metadata = json.loads(files.pop(META))
    if (
        metadata.get("version") != 1
        or metadata.get("revision") != revision
        or metadata.get("source_sha256") != expected_source
        or inventory(files) != metadata.get("files")
        or any(not asset(name) for name in files)
    ):
        raise ValueError("source bundle contains unbound or executable/nonasset paths")
    registry = yaml.safe_load(files["ansible/roles/shared_data/files/registry.yaml"])
    if sha(canonical({"registry": registry, "revision": revision})) != expected_source:
        raise ValueError("source bundle registry differs from bootstrap source")
    destination = Path(destination)
    if (
        destination.is_symlink()
        or not destination.is_dir()
        or any(destination.iterdir())
    ):
        raise ValueError("source extraction requires an empty real private directory")
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
    (destination / META).write_bytes(canonical(metadata))
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=[
            "source",
            "build-context",
            "image-provenance",
            "verify-image",
            "unpack",
        ],
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--input")
    parser.add_argument("--destination")
    parser.add_argument("--sha256")
    parser.add_argument("--source-sha256")
    parser.add_argument("--code-sha256")
    args = parser.parse_args()
    if args.action == "source":
        print(
            json.dumps(
                source_bundle(committed(args.root, args.revision), args.revision)
            )
        )
    elif args.action == "build-context":
        import sys

        sys.stdout.buffer.write(
            build_context(committed(args.root, args.revision), args.revision)
        )
    elif args.action == "image-provenance":
        print(
            json.dumps(
                {
                    k: v
                    for k, v in image_provenance(args.root, args.revision).items()
                    if k != "files"
                }
            )
        )
    elif args.action == "verify-image":
        print(
            json.dumps(
                {
                    k: v
                    for k, v in verify_image(args.root, args.code_sha256).items()
                    if k != "files"
                }
            )
        )
    else:
        verify_image(args.root, args.code_sha256)
        print(
            json.dumps(
                unpack(
                    Path(args.input).read_bytes(),
                    args.destination,
                    args.revision,
                    args.sha256,
                    args.source_sha256,
                )
            )
        )


if __name__ == "__main__":
    main()
