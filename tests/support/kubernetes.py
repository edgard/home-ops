"""Render pinned charts and invoke native validators in a pytest-owned workspace."""

import hashlib
import os
from pathlib import Path
import stat
import subprocess
import time

from tests.support.runtime import environment, run_command
from tests.support.schemas import export
from tests.support.sources import applications, manifest_paths, read_yaml


def render_validate(root, output, *, env=None):
    root, output = Path(root), Path(output)
    try:
        info = output.lstat()
        private = (
            stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.getuid()
        )
    except FileNotFoundError:
        private = False
    if not private or any(output.iterdir()):
        raise ValueError(
            "Validation output must be an empty private directory without symlinks"
        )

    apps = applications(root)
    sources = manifest_paths(root)
    discovered = {
        path
        for path in (root / "apps").rglob("*.yaml")
        if "manifests" in path.relative_to(root / "apps").parts
    }
    assert discovered == {
        path for path in sources if path.is_relative_to(root / "apps")
    }, "unsupported manifest layout"
    assert (root / "argocd").is_dir(), "missing Argo CD sources"
    version = read_yaml(
        root
        / "apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
    )["spec"]["kubernetes"]["version"]
    assert isinstance(version, str) and version, "missing Kubernetes target version"
    raw = sorted({root / "argocd", *(path.parent for path in discovered)})
    tool_env = environment(output, env)
    tool_env.update(
        {
            "HELM_CONFIG_HOME": str(output / "helm/config"),
            "HELM_CACHE_HOME": str(output / "helm/cache"),
            "HELM_DATA_HOME": str(output / "helm/data"),
            "HELM_REPOSITORY_CONFIG": str(output / "helm/config/repositories.yaml"),
            "HELM_REPOSITORY_CACHE": str(output / "helm/cache/repository"),
            "HELM_REGISTRY_CONFIG": str(output / "helm/config/registry/config.json"),
            "HELM_CONTENT_CACHE": str(output / "helm/cache/content"),
        }
    )
    for directory in (
        "helm",
        "helm/config",
        "helm/config/registry",
        "helm/cache",
        "helm/cache/content",
        "helm/cache/repository",
        "helm/data",
        "charts",
        "rendered",
        "schemas",
    ):
        (output / directory).mkdir(mode=0o700)
    deadline = time.monotonic() + 900

    def run(args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, 900)
        try:
            return run_command(
                [str(arg) for arg in args],
                cwd=root,
                env=tool_env,
                timeout=min(300, remaining),
                check=True,
            )
        except subprocess.CalledProcessError as error:
            error.add_note(error.stdout + error.stderr)
            raise

    rendered = []
    for app in apps:
        chart = app.metadata["chart"]
        repo, pin = chart["repo"], chart["version"]
        name = chart.get("name", repo.rsplit("/", 1)[-1])
        assert (
            name and Path(name).name == name and name not in {".", ".."}
        ), "invalid chart name"
        key = hashlib.sha256(f"{repo}|{chart.get('name', '')}|{pin}".encode()).hexdigest()
        cache = output / "charts" / key
        cache.mkdir(mode=0o700, exist_ok=True)
        if not (cache / name).exists():
            pull = [
                "helm",
                "pull",
                repo if repo.startswith("oci://") else name,
                "--version",
                pin,
                "--untar",
                "--untardir",
                cache,
            ]
            if not repo.startswith("oci://"):
                pull += ["--repo", repo]
            for attempt in range(4):
                try:
                    run(pull)
                    break
                except subprocess.CalledProcessError:
                    if attempt == 3:
                        raise
                    time.sleep(3)
        result = run(
            [
                "helm",
                "template",
                "test",
                cache / name,
                "--include-crds",
                "--values",
                app.path / "values.yaml",
                "--kube-version",
                version.removeprefix("v"),
                "--api-versions",
                "gateway.networking.k8s.io/v1/HTTPRoute",
            ]
        )
        directory = output / "rendered" / app.category
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / (app.name + ".yaml")
        target.write_text(result.stdout)
        target.chmod(0o600)
        assert read_yaml(
            target, multiple=True
        ), f"application rendered no resources: {app.path}"
        rendered.append(target)

    export(output / "schemas", sources + rendered)
    template = "{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
    schema_args = [
        "kubeconform",
        "-kubernetes-version",
        version.removeprefix("v"),
        "-schema-location",
        str(output / "schemas") + "/" + template,
        "-schema-location",
        "default",
        "-schema-location",
        "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/" + template,
    ]
    run(
        schema_args
        + [
            "-skip",
            "CustomResourceDefinition,renovate-operator.mogenius.com/v1alpha1/RenovateJob",
            *raw,
        ]
    )
    for path in raw:
        run(
            [
                "pluto",
                "detect-files",
                "-d",
                path,
                "--target-versions",
                f"k8s={version}",
                "-o",
                "wide",
            ]
        )
    run(schema_args + ["-skip", "CustomResourceDefinition", *rendered])
    run(
        [
            "pluto",
            "detect-files",
            "-d",
            output / "rendered",
            "--target-versions",
            f"k8s={version}",
            "-o",
            "wide",
        ]
    )
