import pytest

from tests.support.kubernetes import render_validate


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
    with pytest.raises(ValueError, match="empty private directory without symlinks"):
        render_validate(tmp_path, output)
    if invalid == "nonempty":
        assert (output / "keep").read_text() == "preserve"
