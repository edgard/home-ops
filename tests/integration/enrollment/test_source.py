"""Verify source binding using real local Git, without contacting a cluster."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.support.runtime import ROOT

ROLE = ROOT / "ansible/roles/shared_data"


def source_module():
    path = ROLE / "files/enrollment_source.py"
    assert path.is_file(), "Missing exact Git/Helm source verifier"
    spec = importlib.util.spec_from_file_location("enrollment_source", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_rejects_unsupported_revision_and_non_shutdown_resource_change():
    m = source_module()
    with pytest.raises(ValueError, match="40"):
        m.verify_revision(".", "master")
    old = [
        {
            "kind": "Service",
            "metadata": {"name": "paperless-main"},
            "spec": {"selector": {"app": "main"}},
        }
    ]
    new = json.loads(json.dumps(old))
    new[0]["spec"]["selector"] = {"app": "different"}
    with pytest.raises(ValueError, match="shutdown-only"):
        m.validate_rendered_delta(old, new)


def test_actual_git_revision_is_resolved_and_dirty_app_is_rejected(tmp_path):
    m = source_module()
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    app = tmp_path / "apps/selfhosted/paperless"
    app.mkdir(parents=True)
    (app / "values.yaml").write_text("hello: original\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "synthetic",
        ],
        check=True,
    )
    rev = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    assert m.verify_revision(tmp_path, rev) == rev
    (app / "values.yaml").write_text("hello: dirty\n")
    with pytest.raises(ValueError, match="clean"):
        m.verify_revision(tmp_path, rev)


def test_real_git_helm_binds_only_shutdown_diff(tmp_path):
    m = source_module()
    repo = tmp_path / "synthetic-repo"
    app = repo / "apps/selfhosted/paperless"
    app.mkdir(parents=True)
    for filename in ["values.yaml", "app.yaml"]:
        (app / filename).write_text(
            (Path.cwd() / "apps/selfhosted/paperless" / filename).read_text()
        )

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], text=True
        ).strip()

    git("init", "-q")
    git("add", ".")
    git(
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "Original source",
    )
    original = git("rev-parse", "HEAD")
    values = yaml.safe_load((app / "values.yaml").read_text())
    main = values["controllers"]["main"]
    main["pod"] = {"terminationGracePeriodSeconds": 2000}
    container = main["containers"]["app"]
    container["image"]["digest"] = (
        "sha256:9bc6e8248891bcfa6f52fffe8b81e4ea8cae75790c3ec1b9906961a7ba55c969"
    )
    container["env"].update(PAPERLESS_WORKER_TIMEOUT="1800", S6_KILL_GRACETIME="3000")
    container["probes"]["liveness"] = {
        "enabled": True,
        "custom": True,
        "spec": {
            "exec": {
                "command": [
                    "sh",
                    "-c",
                    'test "$(s6-svstat -o up /run/service/svc-worker)" = true',
                ]
            },
            "periodSeconds": 10,
            "timeoutSeconds": 3,
            "failureThreshold": 6,
        },
    }
    (app / "values.yaml").write_text(yaml.safe_dump(values, sort_keys=False))
    git("add", ".")
    git(
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "Reviewed shutdown settings",
    )
    desired = git("rev-parse", "HEAD")
    before, _ = m.render(repo, original)
    after, _ = m.render(repo, desired)
    proof = m.validate_rendered_delta(before, after)
    assert proof["original_sha256"] != proof["desired_sha256"]
    assert proof["template"]["spec"]["terminationGracePeriodSeconds"] == 2000
    # A same-source-label payload cannot smuggle a Redis cutover through this verifier.
    values["controllers"]["main"]["containers"]["app"]["env"]["PAPERLESS_REDIS"] = (
        "redis://shared:6379"
    )
    (app / "values.yaml").write_text(yaml.safe_dump(values, sort_keys=False))
    git("add", ".")
    git(
        "-c",
        "user.name=Synthetic",
        "-c",
        "user.email=synthetic@example.invalid",
        "commit",
        "-qm",
        "Unsupported cutover",
    )
    bad, _ = m.render(repo, git("rev-parse", "HEAD"))
    with pytest.raises(ValueError, match="shutdown-only"):
        m.validate_rendered_delta(before, bad)


def test_live_helm_override_is_rejected_before_git_or_render():
    m = source_module()
    application = {
        "metadata": {"name": "paperless"},
        "spec": {
            "destination": {"namespace": "selfhosted"},
            "sources": [
                {
                    "repoURL": "oci://ghcr.io/bjw-s-labs/helm/app-template",
                    "path": ".",
                    "helm": {"values": "malicious: override"},
                }
            ],
        },
    }
    with pytest.raises(ValueError, match="Helm inputs"):
        m.resolve_desired("unused", application)


def source_application():
    repository = "https://github.com/edgard/home-ops.git"
    return {
        "metadata": {"name": "paperless"},
        "spec": {
            "destination": {"namespace": "selfhosted"},
            "sources": [
                {
                    "repoURL": "oci://ghcr.io/bjw-s-labs/helm/app-template",
                    "chart": "",
                    "path": ".",
                    "targetRevision": "5.3.0",
                    "helm": {
                        "valueFiles": ["$values/apps/selfhosted/paperless/values.yaml"]
                    },
                },
                {"repoURL": repository, "targetRevision": "master", "ref": "values"},
                {
                    "repoURL": repository,
                    "targetRevision": "master",
                    "path": "apps/selfhosted/paperless",
                    "directory": {
                        "recurse": True,
                        "include": "{manifests/*.yaml,manifests/*.yml}",
                    },
                },
            ],
        },
    }


def synthetic_source_reads(monkeypatch, module):
    """Only external Git reads are replaced; exercise the exact source validator."""
    calls = []
    revision = "a" * 40

    def command(args):
        calls.append(args)
        if args[-3:] == ["remote", "get-url", "origin"]:
            return "https://github.com/edgard/home-ops.git\n"
        if args[-4:] == ["ls-remote", "--refs", "origin", "refs/heads/master"]:
            return revision + "\trefs/heads/master\n"
        raise AssertionError(args)

    monkeypatch.setattr(module, "command", command)
    monkeypatch.setattr(module, "verify_revision", lambda _repo, value: value)
    monkeypatch.setattr(module, "git_file", lambda *_args: "chart:\n  version: 5.3.0\n")
    return calls, revision


@pytest.mark.parametrize("reverse_git_sources", [False, True])
def test_exact_values_and_raw_sources_are_accepted(monkeypatch, reverse_git_sources):
    m = source_module()
    calls, revision = synthetic_source_reads(monkeypatch, m)
    application = source_application()
    if reverse_git_sources:
        application["spec"]["sources"][1:] = reversed(
            application["spec"]["sources"][1:]
        )
    assert m.resolve_desired("synthetic", application) == revision
    assert len(calls) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "values_path",
        "values_directory",
        "values_plugin",
        "values_helm",
        "raw_recurse",
        "raw_include",
        "raw_exclude",
        "raw_plugin",
        "raw_helm",
        "raw_kustomize",
        "raw_ref",
    ],
)
def test_git_source_generation_outside_rendered_proof_is_rejected_before_reads(
    monkeypatch, mutation
):
    m = source_module()
    calls, _revision = synthetic_source_reads(monkeypatch, m)
    application = source_application()
    values, raw = application["spec"]["sources"][1:]
    if mutation == "values_path":
        values.update(
            path="apps/platform-system/postgresql/manifests",
            directory={"recurse": True},
        )
    elif mutation == "values_directory":
        values["directory"] = {"recurse": True}
    elif mutation == "values_plugin":
        values["plugin"] = {"name": "extra-generation"}
    elif mutation == "values_helm":
        values["helm"] = {"values": "extra: resource"}
    elif mutation == "raw_recurse":
        raw["directory"]["recurse"] = False
    elif mutation == "raw_include":
        raw["directory"]["include"] = "**/*.yaml"
    elif mutation == "raw_exclude":
        raw["directory"]["exclude"] = "**/ignored.yaml"
    elif mutation == "raw_plugin":
        raw["plugin"] = {"name": "extra-generation"}
    elif mutation == "raw_helm":
        raw["helm"] = {"parameters": [{"name": "extra", "value": "true"}]}
    elif mutation == "raw_kustomize":
        raw["kustomize"] = {"namePrefix": "extra-"}
    else:
        raw["ref"] = "values"
    with pytest.raises(ValueError, match="Application sources"):
        m.resolve_desired("synthetic", application)
    assert not calls, (
        "Unproved source generation must fail before deriving source proof"
    )
