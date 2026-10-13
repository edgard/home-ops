import pytest

from tests.support.applications import assert_application, assert_app_configuration
from tests.support.kubernetes import render_validate
from tests.support.sources import applications, read_yaml


@pytest.fixture(scope="session")
def rendered(tmp_path_factory, repo_root):
    apps = applications(repo_root)
    for app in apps:
        assert_application(app)
        assert_app_configuration(app)
    workspace = tmp_path_factory.mktemp("kubernetes output")
    output = workspace / "output"
    output.mkdir(mode=0o700)
    try:
        render_validate(repo_root, output)
        expected = {
            output / "rendered" / app.category / (app.name + ".yaml") for app in apps
        }
        assert set((output / "rendered").glob("*/*.yaml")) == expected
        by_app = {path: read_yaml(path, multiple=True) for path in sorted(expected)}
        assert all(by_app.values()), "an application rendered no resources"
        documents = [doc for docs in by_app.values() for doc in docs]
        assert documents, "chart rendering produced no resources"
        yield documents
    finally:
        import shutil

        if output.exists():
            shutil.rmtree(output)
