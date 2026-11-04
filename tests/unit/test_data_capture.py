import hashlib
import json
import sys
from unittest.mock import patch

import pytest

from tests.support.runtime import load_module


def module():
    with patch.dict(
        sys.modules, {"data_tools": load_module("shared_data/files/data_tools.py")}
    ):
        return load_module("shared_data/files/capture.py")


def test_capture_space_counts_selected_files_and_twenty_percent(tmp_path):
    source = tmp_path / "source"
    (source / "selfhosted/demo").mkdir(parents=True)
    (source / "selfhosted/demo/file").write_bytes(b"x" * 100)
    assert module().required_bytes(source, ["selfhosted/demo"]) == 240


def test_capture_rejects_symlinked_pvc(tmp_path):
    source = tmp_path / "source"
    (source / "selfhosted").mkdir(parents=True)
    (source / "selfhosted/demo").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        module().required_bytes(source, ["selfhosted/demo"])


def test_publish_requires_manifest_and_never_reuses_generation(tmp_path):
    stage, published = tmp_path / "in-progress", tmp_path / "generations/op"
    stage.mkdir()
    with pytest.raises(ValueError):
        module().publish(stage, published)
    (stage / ".home-ops").mkdir()
    dump = stage / "selfhosted/demo/.home-ops/databases/demo.dump"
    dump.parent.mkdir(parents=True)
    dump.write_bytes(b"dump")
    (stage / ".home-ops/manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "consumers": {
                    "demo": {
                        "backend": "postgresql",
                        "databases": [{"name": "demo", "owner": "demo"}],
                        "pvcs": ["selfhosted/demo"],
                        "images": ["example/demo:1"],
                    }
                },
                "files": {
                    "selfhosted/demo/.home-ops/databases/demo.dump": hashlib.sha256(
                        b"dump"
                    ).hexdigest()
                },
            }
        )
    )
    module().publish(stage, published)
    assert published.is_dir() and not stage.exists()
    stage.mkdir()
    with pytest.raises(ValueError):
        module().publish(stage, published)


def test_cleanup_does_not_remove_unuploaded_generations(tmp_path):
    for name in ["one", "two", "pending"]:
        p = tmp_path / name
        (p / ".home-ops").mkdir(parents=True)
        (p / ".home-ops/manifest.json").write_text("{}")
        if name != "pending":
            (p / ".home-ops/uploaded.json").write_text("{}")
    module().prune_generations(tmp_path)
    assert (tmp_path / "pending").exists()
    assert len(list(tmp_path.iterdir())) == 2
