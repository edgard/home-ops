import pytest

from tests.support.runtime import run_role


@pytest.mark.parametrize("invalid", ["missing", "nonempty", "public", "symlink"])
def test_pipeline_rejects_unsafe_output_workspace(tmp_path, invalid):
    output = tmp_path / "output"
    if invalid != "missing":
        output.mkdir(mode=0o700)
    if invalid == "nonempty":
        (output / "keep").write_text("preserve")
    if invalid == "public":
        output.chmod(0o755)
    if invalid == "symlink":
        link = tmp_path / "link"
        link.symlink_to(output, target_is_directory=True)
        output = link
    result = run_role(
        tmp_path, "kubernetes_validation", "main", {"kubernetes_validation_output_dir": str(output)}
    )
    assert result.returncode != 0
    assert "empty private directory without symlinks" in result.stdout + result.stderr
    if invalid == "nonempty":
        assert (output / "keep").read_text() == "preserve"
