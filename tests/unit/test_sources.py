import pytest

from tests.support.sources import read_yaml, applications


def test_source_loader_preserves_types_and_document_order(tmp_path):
    source = tmp_path / "values.yaml"
    source.write_text("enabled: true\nreplicas: 1\n---\ndefault: =\n")
    assert read_yaml(source, multiple=True) == [{"enabled": True, "replicas": 1}, {"default": "="}]


@pytest.mark.parametrize("text", ["!!python/object/apply:os.system [false]", "value: ["])
def test_source_loader_rejects_unsafe_or_malformed_yaml(tmp_path, text):
    source = tmp_path / "broken.yaml"
    source.write_text(text)
    with pytest.raises((ValueError, AssertionError)):
        read_yaml(source)


def test_application_discovery_requires_complete_sources(tmp_path):
    app = tmp_path / "apps/category/example"
    app.mkdir(parents=True)
    (app / "values.yaml").write_text("controllers: {}\n")
    with pytest.raises(AssertionError, match="app.yaml"):
        applications(tmp_path)


def test_empty_application_discovery_fails(tmp_path):
    with pytest.raises(AssertionError, match="applications"):
        applications(tmp_path)


@pytest.mark.parametrize("missing", ["app.yaml", "values.yaml"])
def test_missing_application_input(tmp_path, missing):
    app = tmp_path / "apps/category/demo"
    app.mkdir(parents=True)
    for name in ["app.yaml", "values.yaml"]:
        if name != missing:
            (app / name).write_text("{}\n")
    with pytest.raises(AssertionError, match=missing):
        applications(tmp_path)


@pytest.mark.parametrize("content", ["", "---\n", "[]\n", "true\n"])
def test_empty_or_wrong_type_application_input(tmp_path, content):
    app = tmp_path / "apps/category/demo"
    app.mkdir(parents=True)
    (app / "app.yaml").write_text("{}\n")
    (app / "values.yaml").write_text(content)
    with pytest.raises(AssertionError):
        applications(tmp_path)
