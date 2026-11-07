"""Source interfaces that keep the cold worker bounded and natively buildable."""

import yaml

from tests.support.runtime import ROOT


def test_cold_helm_disables_hooks_and_delays_argocd_route():
    tasks = yaml.safe_load(
        (ROOT / "ansible/roles/platform/tasks/install_release.yml").read_text()
    )
    install = next(
        t["kubernetes.core.helm"] for t in tasks if "kubernetes.core.helm" in t
    )
    assert (
        install["disable_hook"]
        == "{{ true if platform_recovery_mode | bool else omit }}"
    )
    assert "platform_cold_helm_values" in install["release_values"]
    defaults = yaml.safe_load(
        (ROOT / "ansible/roles/platform/defaults/main.yml").read_text()
    )
    assert defaults["platform_cold_helm_values"]["argocd"] == {
        "server": {"httproute": {"enabled": False}},
        "redisSecretInit": {"enabled": False},
        "redis": {"existingSecret": "argocd-redis"},
    }
    argocd = yaml.safe_load(
        (ROOT / "ansible/roles/platform/tasks/argocd.yml").read_text()
    )
    secret = next(
        i
        for i, t in enumerate(argocd)
        if t.get("ansible.builtin.include_tasks") == "recovery_argocd_cache.yml"
    )
    install_index = next(
        i
        for i, t in enumerate(argocd)
        if t.get("ansible.builtin.include_tasks") == "install_release.yml"
    )
    assert secret < install_index


def test_native_image_and_workflow_use_committed_public_context():
    dockerfile = (ROOT / "containers/data-tools/Dockerfile").read_text()
    assert "COPY . " not in dockerfile and "COPY ./" not in dockerfile
    assert "install_helm.py" in dockerfile
    assert "image-provenance" in dockerfile
    assert "RUN chmod -R a+rX /opt/home-ops" in dockerfile
    assert "HOME_OPS_SOURCE_REVISION" in dockerfile
    workflow = (ROOT / ".github/workflows/data-tools.yml").read_text()
    assert "cold_bundle.py build-context" in workflow
    assert "GITHUB_SHA" in workflow
    assert "verify-image" in workflow
    assert "--user 1000:1000 --read-only" in workflow
    assert "platform-recovery-executor.yml" in workflow
    assert "docker build --build-arg HOME_OPS_SOURCE_REVISION=" in workflow
    installer = (ROOT / "containers/data-tools/install_helm.py").read_text()
    assert "aarch64" in installer and "x86_64" in installer
