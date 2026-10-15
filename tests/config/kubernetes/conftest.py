import json
import shutil
import traceback

from filelock import FileLock
import pytest

from tests.support.applications import assert_application, assert_app_configuration
from tests.support.kubernetes import render_validate
from tests.support.sources import applications, read_yaml


@pytest.fixture(scope="session")
def rendered(tmp_path_factory, repo_root, worker_id):
    shared = tmp_path_factory.getbasetemp()
    if worker_id != "master":
        shared = shared.parent
    snapshot = shared / "rendered.json"
    failure = shared / "rendered.failure"
    # The native pipeline has a 900-second deadline; bound lock waits as well.
    with FileLock(shared / "rendered.lock", timeout=960):
        if failure.exists():
            pytest.fail(failure.read_text(), pytrace=False)
        if not snapshot.exists():
            # A terminated initializer must not leave a reusable partial result.
            failure.write_text(
                "Kubernetes rendering was interrupted before publication"
            )
            failure.chmod(0o600)
            output = tmp_path_factory.mktemp("kubernetes output") / "output"
            try:
                apps = applications(repo_root)
                for app in apps:
                    assert_application(app)
                    assert_app_configuration(app)
                output.mkdir(mode=0o700)
                try:
                    render_validate(repo_root, output)
                    expected = {
                        output / "rendered" / app.category / (app.name + ".yaml")
                        for app in apps
                    }
                    assert (
                        set((output / "rendered").glob("*/*.yaml")) == expected
                    ), "rendered application inventory differs from sources"
                    by_app = {
                        path: read_yaml(path, multiple=True)
                        for path in sorted(expected)
                    }
                    assert all(by_app.values()), "an application rendered no resources"
                    documents = [doc for docs in by_app.values() for doc in docs]
                    assert documents, "chart rendering produced no resources"
                finally:
                    shutil.rmtree(output)

                temporary = shared / "rendered.json.tmp"
                temporary.write_text(json.dumps(documents))
                temporary.chmod(0o600)
                temporary.replace(snapshot)
                failure.unlink()
            except BaseException:
                failure.write_text(traceback.format_exc())
                raise
        # Each worker owns its parsed objects; consumers never mutate the snapshot.
        return json.loads(snapshot.read_text())
