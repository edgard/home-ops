"""Render two exact local Git revisions; no Kubernetes or credential access.

Only invoked by the operator's local role. The live actor receives this derived
nonsecret proof, never a free-form desired manifest supplied by the operator.
"""

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

APP = "apps/selfhosted/paperless"


def command(args):
    return subprocess.check_output([str(arg) for arg in args], text=True, timeout=120)


def verify_revision(repo, revision):
    if not re.fullmatch("[a-f0-9]{40}", revision):
        raise ValueError("an exact 40-hex source revision is required")
    if (
        command(["git", "-C", repo, "rev-parse", revision + "^{commit}"]).strip()
        != revision
    ):
        raise ValueError("source revision does not identify that exact commit")
    if command(
        ["git", "-C", repo, "status", "--porcelain", "--untracked-files=all", "--", APP]
    ).strip():
        raise ValueError("Paperless source must be clean before enrollment rendering")
    return revision


def git_file(repo, revision, path):
    return command(["git", "-C", repo, "show", revision + ":" + path])


def render(repo, revision):
    verify_revision(repo, revision)
    app = yaml.safe_load(git_file(repo, revision, APP + "/app.yaml"))
    chart = app["chart"]
    if (
        chart["repo"] != "oci://ghcr.io/bjw-s-labs/helm/app-template"
        or chart.get("path") != "."
    ):
        raise ValueError("unreviewed chart source")
    # app.yaml + values.yaml are the complete chart inputs for this application.
    files = command(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", revision, "--", APP]
    ).splitlines()
    if set(files) != {APP + "/app.yaml", APP + "/values.yaml"}:
        raise ValueError("unreviewed additional Paperless source files")
    values = git_file(repo, revision, APP + "/values.yaml")
    with tempfile.TemporaryDirectory(
        prefix="paperless-enrollment-source-"
    ) as directory:
        path = Path(directory) / "values.yaml"
        path.write_text(values)
        manifests = list(
            yaml.safe_load_all(
                command(
                    [
                        "helm",
                        "template",
                        "paperless",
                        chart["repo"],
                        "--version",
                        chart["version"],
                        "--namespace",
                        "selfhosted",
                        "--values",
                        path,
                    ]
                )
            )
        )
    return [row for row in manifests if row], chart


def enrollment_filters():
    path = Path(__file__).resolve().parents[1] / "filter_plugins/enrollment.py"
    spec = importlib.util.spec_from_file_location("enrollment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_rendered_delta(original, desired):
    m = enrollment_filters()

    def keyed(rows):
        return {(row["kind"], row["metadata"]["name"]): row for row in rows}

    old, new = keyed(original), keyed(desired)
    key = ("Deployment", "paperless-main")
    if set(old) != set(new) or key not in old:
        raise ValueError("source must retain the shutdown-only resource inventory")
    result = m.shared_data_enrollment_delta(
        old[key]["spec"]["template"], new[key]["spec"]["template"]
    )
    import copy

    normalized = copy.deepcopy(new)
    normalized[key]["spec"]["template"] = old[key]["spec"]["template"]
    if normalized != old:
        raise ValueError("source includes a non shutdown-only resource change")
    return {
        **result,
        "template": new[key]["spec"]["template"],
        "source_template": old[key]["spec"]["template"],
    }


def resolve_desired(repo, application):
    sources = application["spec"]["sources"]
    if (
        application["metadata"]["name"] != "paperless"
        or application["spec"].get("destination", {}).get("namespace") != "selfhosted"
    ):
        raise ValueError("unreviewed application release or namespace")
    chart_sources = [
        row
        for row in sources
        if row.get("repoURL") == "oci://ghcr.io/bjw-s-labs/helm/app-template"
    ]
    if (
        len(chart_sources) != 1
        or chart_sources[0].get("path") != "."
        or chart_sources[0].get("chart", "") != ""
        or chart_sources[0].get("helm")
        != {"valueFiles": ["$values/apps/selfhosted/paperless/values.yaml"]}
        or set(chart_sources[0])
        - {"repoURL", "chart", "path", "targetRevision", "helm"}
    ):
        raise ValueError("unreviewed Helm inputs or overrides")
    git_sources = [
        row
        for row in sources
        if row.get("repoURL") == "https://github.com/edgard/home-ops.git"
    ]
    if (
        len(sources) != 3
        or len(git_sources) != 2
        or len({row["targetRevision"] for row in git_sources}) != 1
    ):
        raise ValueError("unreviewed Paperless Application sources")
    revision = git_sources[0]["targetRevision"]
    common = {
        "repoURL": "https://github.com/edgard/home-ops.git",
        "targetRevision": revision,
    }
    values_source = {**common, "ref": "values"}
    manifests_source = {
        **common,
        "path": APP,
        "directory": {
            "recurse": True,
            "include": "{manifests/*.yaml,manifests/*.yml}",
        },
    }
    # A values ref with a path can also generate manifests. Bind both complete
    # Git definitions to the ApplicationSet before any source proof is derived.
    if (
        sum(source == values_source for source in git_sources) != 1
        or sum(source == manifests_source for source in git_sources) != 1
    ):
        raise ValueError("unreviewed Paperless Application sources")
    origin = command(["git", "-C", repo, "remote", "get-url", "origin"]).strip()
    if origin not in {
        "https://github.com/edgard/home-ops.git",
        "git@github.com:edgard/home-ops.git",
    }:
        raise ValueError("local origin differs from the registered source")
    if revision == "master":
        result = command(
            ["git", "-C", repo, "ls-remote", "--refs", "origin", "refs/heads/master"]
        ).split()
        if len(result) != 2 or result[1] != "refs/heads/master":
            raise ValueError("cannot resolve current registered source")
        revision = result[0]
    verify_revision(repo, revision)
    chart = yaml.safe_load(git_file(repo, revision, APP + "/app.yaml"))["chart"]
    if chart_sources[0]["targetRevision"] != chart["version"]:
        raise ValueError("live Application chart differs from exact source revision")
    return revision


def main(repo, original, desired, application_json=""):
    if application_json:
        actual = resolve_desired(repo, json.loads(application_json))
        if desired and desired != actual:
            raise ValueError(
                "requested revision is not current registered desired source"
            )
        desired = actual
    before, old_chart = render(repo, original)
    after, new_chart = render(repo, desired)
    if old_chart != new_chart:
        raise ValueError("chart changes are outside grace enrollment")
    proof = validate_rendered_delta(before, after)
    proof.update(
        {
            "source_revision": original,
            "target_revision": desired,
            "chart": new_chart,
            "registered_desired_verified": bool(application_json),
        }
    )
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main(*sys.argv[1:])
