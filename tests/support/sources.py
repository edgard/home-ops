"""Read authoritative sources without policy-specific inventories."""

from dataclasses import dataclass
from pathlib import Path
import tomllib

import json5
import yaml


class KubernetesLoader(yaml.SafeLoader):
    """Safe Kubernetes YAML, including an unquoted '=' chart scalar."""


KubernetesLoader.add_constructor(
    "tag:yaml.org,2002:value", KubernetesLoader.construct_scalar
)


def read_yaml(path, multiple=False):
    path = Path(path)
    try:
        documents = list(yaml.load_all(path.read_text(), Loader=KubernetesLoader))
    except yaml.YAMLError:
        raise ValueError(f"invalid YAML: {path}") from None
    if multiple:
        return [document for document in documents if document is not None]
    assert (
        len(documents) == 1 and documents[0] is not None
    ), f"empty or multiple documents: {path}"
    return documents[0]


def read_toml(path):
    return tomllib.loads(Path(path).read_text())


def read_json5(path):
    return json5.loads(Path(path).read_text(), allow_duplicate_keys=False)


@dataclass(frozen=True)
class Application:
    path: Path
    metadata: dict
    values: dict
    documents: list

    @property
    def name(self):
        return self.path.name

    @property
    def category(self):
        return self.path.parent.name


def applications(root):
    paths = sorted(path for path in (Path(root) / "apps").glob("*/*") if path.is_dir())
    assert paths, f"no applications discovered: {root}"
    result = []
    for path in paths:
        for name in ("app.yaml", "values.yaml"):
            assert (path / name).is_file(), f"missing {path / name}"
        metadata, values = (read_yaml(path / name) for name in ("app.yaml", "values.yaml"))
        assert isinstance(metadata, dict) and isinstance(
            values, dict
        ), f"invalid application: {path}"
        documents = [
            doc
            for source in sorted((path / "manifests").glob("*.yaml"))
            for doc in read_yaml(source, multiple=True)
        ]
        result.append(Application(path, metadata, values, documents))
    return result


def manifest_paths(root):
    root = Path(root)
    paths = sorted((root / "argocd").rglob("*.yaml")) + sorted(
        (root / "apps").glob("*/*/manifests/*.yaml")
    )
    assert paths, f"no manifests discovered: {root}"
    assert len(paths) == len(set(paths)), "duplicate manifest discovery"
    return paths
