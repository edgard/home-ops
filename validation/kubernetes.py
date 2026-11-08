"""Serial Helm, kubeconform and Pluto validation; no pytest or cluster access."""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from validation.data import check_paperless, check_resources
from validation.schemas import SchemaError, export
from validation.sources import SourceError, applications, manifest_paths, read_yaml


def validate(root):
    apps = applications(root)
    sources = manifest_paths(root)
    assert len({app.name for app in apps}) == len(apps), "duplicate application names"
    version = read_yaml(
        root
        / "apps/platform-system/tuppr/manifests/tuppr-kubernetes.kubernetesupgrade.yaml"
    )["spec"]["kubernetes"]["version"]
    assert isinstance(version, str) and version, "missing Kubernetes target"
    raw_documents = [doc for path in sources for doc in read_yaml(path, multiple=True)]
    check_resources(raw_documents)
    with TemporaryDirectory(prefix="home-ops-validation-") as temporary:
        output = Path(temporary)
        env = {
            key: os.environ[key]
            for key in ("PATH", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "LC_CTYPE")
            if key in os.environ
        }
        env["HOME"] = str(output)
        for name, directory in {
            "HELM_CONFIG_HOME": "helm/config",
            "HELM_CACHE_HOME": "helm/cache",
            "HELM_DATA_HOME": "helm/data",
            "HELM_CONTENT_CACHE": "helm/cache/content",
        }.items():
            path = output / directory
            path.mkdir(parents=True, exist_ok=True)
            env[name] = str(path)
        env.update(
            HELM_REPOSITORY_CONFIG=str(output / "helm/config/repositories.yaml"),
            HELM_REPOSITORY_CACHE=str(output / "helm/cache/repository"),
            HELM_REGISTRY_CONFIG=str(output / "helm/config/registry/config.json"),
        )
        deadline = time.monotonic() + 900

        def run(args, label, attempts=1):
            for attempt in range(attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"{label}: validation deadline exceeded")
                try:
                    result = subprocess.run(
                        [str(arg) for arg in args],
                        cwd=root,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=min(300, remaining),
                    )
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise RuntimeError(f"{label}: {type(error).__name__}") from None
                if result.returncode == 0:
                    return result.stdout
                if attempt + 1 < attempts:
                    time.sleep(3)
            # Tool output can contain configuration values, even on stderr.
            # Report resource identities and HTTP status codes, never payloads.
            hints = re.findall(
                r"(?:status code|HTTP[/\d.]*)[ :]+([45]\d\d)\b", result.stderr
            )
            if args[0] == "kubeconform":
                try:
                    for resource in json.loads(result.stdout).get("resources", []):
                        if resource.get("status") != "statusValid":
                            print(
                                f"{label}: {resource.get('filename')}: "
                                f"{resource.get('kind')}/{resource.get('name')}: "
                                f"{resource.get('status')}",
                                file=sys.stderr,
                            )
                except ValueError, AttributeError, TypeError:
                    pass
            detail = ", HTTP " + ",".join(sorted(set(hints))) if hints else ""
            raise RuntimeError(
                f"{label}: exit {result.returncode}{detail}; tool payload omitted"
            )

        charts, rendered = {}, []
        for app in apps:
            label = f"{app.category}/{app.name}"
            print(f"Validating {label}", flush=True)
            chart = app.metadata["chart"]
            repo, pin = chart["repo"], chart["version"]
            assert isinstance(repo, str) and isinstance(pin, str) and repo and pin, (
                f"{label}: missing chart repository/version"
            )
            name = chart.get("name", repo.rsplit("/", 1)[-1])
            assert name and Path(name).name == name and name not in {".", ".."}, (
                f"{label}: invalid chart name"
            )
            key = (repo, name, pin)
            if key not in charts:
                directory = output / "charts" / str(len(charts))
                directory.mkdir(parents=True)
                pull = [
                    "helm",
                    "pull",
                    repo if repo.startswith("oci://") else name,
                    "--version",
                    pin,
                    "--untar",
                    "--untardir",
                    directory,
                ]
                if not repo.startswith("oci://"):
                    pull += ["--repo", repo]
                run(pull, f"{label}: helm pull {name}@{pin}", attempts=4)
                charts[key] = directory / name
            text = run(
                [
                    "helm",
                    "template",
                    "test",
                    charts[key],
                    "--include-crds",
                    "--values",
                    app.path / "values.yaml",
                    "--kube-version",
                    version.removeprefix("v"),
                    "--api-versions",
                    "gateway.networking.k8s.io/v1/HTTPRoute",
                ],
                f"{label}: helm template ({app.path / 'values.yaml'})",
            )
            target = output / "rendered" / app.category / f"{app.name}.yaml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
            documents = read_yaml(target, multiple=True)
            assert documents, f"{label}: no rendered resources"
            check_resources(documents)
            if app.name == "paperless":
                check_paperless(app.values, documents)
            rendered.append(target)
        export(output / "schemas", sources + rendered)
        template = "{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
        schema_args = [
            "kubeconform",
            "-output",
            "json",
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
                *sources,
            ],
            "raw manifests: kubeconform",
        )
        run(
            schema_args + ["-skip", "CustomResourceDefinition", *rendered],
            "rendered manifests: kubeconform",
        )
        for directory in sorted(
            {path.parent for path in sources} | {output / "rendered"}
        ):
            run(
                [
                    "pluto",
                    "detect-files",
                    "-d",
                    directory,
                    "--target-versions",
                    f"k8s={version}",
                    "-o",
                    "wide",
                ],
                f"{directory}: pluto",
            )
        print(f"Validated {len(apps)} apps and {len(sources)} raw manifest files")


def main():
    try:
        validate(Path(__file__).resolve().parents[1])
    except (
        AssertionError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OSError,
    ) as error:
        # KeyError/TypeError/OSError can embed source values; suppress their text.
        detail = (
            str(error)
            if isinstance(
                error, (AssertionError, RuntimeError, SourceError, SchemaError)
            )
            else type(error).__name__
        )
        print(f"Kubernetes validation failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
