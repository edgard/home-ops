"""Only committed public YAML assets enter an immutable bounded nonexecuting bundle."""

import gzip
import io
import json
import tarfile
from types import SimpleNamespace

import pytest
import yaml

from tests.support.runtime import load_module


def module():
    return load_module("platform/files/cold_bundle.py")


def files():
    return {
        "ansible/roles/shared_data/files/registry.yaml": yaml.safe_dump(
            {"version": 1, "consumers": {}, "file_consumers": {}}
        ).encode(),
        "apps/selfhosted/demo/app.yaml": b"chart: example\n",
        "apps/selfhosted/demo/values.yaml": b"controllers: {}\n",
        "ansible/roles/platform/tasks/bootstrap.yml": b"---\n[]\n",
        "containers/data-tools/Dockerfile": b"FROM example@sha256:pinned\n",
        "ansible/requirements.yml": b"collections: []\n",
    }


def test_bundle_roundtrip_is_checksum_bound_and_nonexecutable(tmp_path):
    b = module()
    proof = b.source_bundle(files(), "a" * 40)
    raw = __import__("base64").b64decode(proof["bundle_base64"])
    root = tmp_path / "source"
    root.mkdir(mode=0o700)
    metadata = b.unpack(
        raw, root, "a" * 40, proof["bundle_sha256"], proof["source_sha256"]
    )
    assert metadata["revision"] == "a" * 40
    assert all(not p.stat().st_mode & 0o111 for p in root.rglob("*") if p.is_file())
    assert not (root / "ansible/roles/platform/tasks/bootstrap.yml").exists()
    assert b.source_bundle(files(), "a" * 40) == proof


@pytest.mark.parametrize("field", ["checksum", "revision", "registry"])
def test_changed_bundle_binding_is_refused_before_extraction(tmp_path, field):
    b = module()
    proof = b.source_bundle(files(), "a" * 40)
    raw = __import__("base64").b64decode(proof["bundle_base64"])
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises(ValueError):
        b.unpack(
            raw,
            root,
            "b" * 40 if field == "revision" else "a" * 40,
            "f" * 64 if field == "checksum" else proof["bundle_sha256"],
            "f" * 64 if field == "registry" else proof["source_sha256"],
        )
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/outside",
        "apps/selfhosted/demo/run.py",
        "ansible/roles/platform/tasks/bootstrap.yml",
    ],
)
def test_traversal_and_executable_nonassets_are_refused(tmp_path, path):
    b = module()
    proof = b.source_bundle(files(), "a" * 40)
    raw = __import__("base64").b64decode(proof["bundle_base64"])
    entries = b.regular_archive(gzip.decompress(raw))
    metadata = json.loads(entries[b.META])
    if path.startswith(("../", "/")):
        # Construct an intentionally unsafe archive without the producer guard.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as archive:
            item = tarfile.TarInfo(path)
            item.size = 1
            archive.addfile(item, io.BytesIO(b"x"))
        malicious = gzip.compress(buf.getvalue())
    else:
        entries[path] = b"not a config"
        metadata["files"][path] = b.sha(entries[path])
        entries[b.META] = b.canonical(metadata)
        malicious = b.archive(entries, compressed=True)
    root = tmp_path / "source"
    root.mkdir()
    with pytest.raises((ValueError, KeyError)):
        b.unpack(malicious, root, "a" * 40, b.sha(malicious), proof["source_sha256"])
    assert list(root.iterdir()) == []


def test_git_snapshot_excludes_ignored_operator_files(tmp_path, monkeypatch):
    b = module()
    operator = tmp_path / "ansible/roles/platform/files/operator.py"
    operator.parent.mkdir(parents=True)
    operator.write_text("PRIVATE_OPERATOR_CANARY")
    snapshot = b.archive(files())
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=snapshot)

    monkeypatch.setattr(b.subprocess, "run", run)
    committed = b.committed(tmp_path, "a" * 40)
    assert "ansible/roles/platform/files/operator.py" not in committed
    assert calls[0][:3] == ["git", "archive", "--format=tar"]
    assert "a" * 40 in calls[0]


def test_build_context_whitelist_and_actual_image_code_provenance(tmp_path):
    b = module()
    values = {
        **files(),
        ".envrc": b"PRIVATE",
        "docs/operator.md": b"PRIVATE",
        ".superpowers/private.yaml": b"PRIVATE",
    }
    context = b.regular_archive(b.build_context(values, "a" * 40))
    assert not {".envrc", "docs/operator.md", ".superpowers/private.yaml"} & set(
        context
    )
    for name, data in context.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    expected = b.code_digest(values)
    proof = b.image_provenance(tmp_path, "a" * 40)
    assert proof["code_sha256"] == expected
    assert b.verify_image(tmp_path, expected)["image_revision"] == "a" * 40
    (tmp_path / "ansible/roles/platform/tasks/bootstrap.yml").write_text("changed")
    with pytest.raises(ValueError):
        b.verify_image(tmp_path, expected)


def test_expanded_archive_size_is_bounded(tmp_path, monkeypatch):
    b = module()
    monkeypatch.setattr(b, "MAX_RAW", 1024)
    raw = gzip.compress(b"x" * 2048)
    with pytest.raises(ValueError):
        b.unpack(raw, tmp_path, "a" * 40, b.sha(raw), "a" * 64)
