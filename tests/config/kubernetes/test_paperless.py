from math import ceil

from tests.support.sources import read_yaml


def test_configured_ocr_image_bound_fits_the_provider_patch_budget(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["gpt"]["containers"]["app"]["env"]
    side = int(env.get("IMAGE_MAX_PIXEL_DIMENSION", 10000))
    assert 0 < side and ceil(side / 32) ** 2 <= 30000


def test_automatic_ocr_preserves_complete_document_text(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["gpt"]["containers"]["app"]["env"]
    assert int(env.get("OCR_LIMIT_PAGES", 5)) == 0, (
        "Automatic OCR replaces searchable content and must include every page"
    )


def test_openai_reasoning_ocr_uses_accepted_temperature(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["gpt"]["containers"]["app"]["env"]
    if env["VISION_LLM_PROVIDER"] == "openai":
        assert float(env.get("VISION_LLM_TEMPERATURE", 0)) == 1


def test_shared_data_keeps_the_same_owner_after_either_app_restarts(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    controllers = values["controllers"]
    main = controllers["main"]["containers"]["app"]["env"]
    gpt = controllers["gpt"]["containers"]["app"]["env"]
    assert int(gpt.get("PUID", 10001)) == int(main["USERMAP_UID"])
    assert int(gpt.get("PGID", 10001)) == int(main["USERMAP_GID"])


def test_gpt_settings_prompts_and_history_survive_pod_replacement(rendered):
    deployment = next(
        doc
        for doc in rendered
        if doc.get("kind") == "Deployment"
        and any(
            container["image"].startswith("icereed/paperless-gpt:")
            for container in doc["spec"]["template"]["spec"]["containers"]
        )
    )
    pod = deployment["spec"]["template"]["spec"]
    persistent = {
        volume["name"]
        for volume in pod.get("volumes", [])
        if "persistentVolumeClaim" in volume
    }
    container = next(c for c in pod["containers"] if c["name"] == "app")
    durable_paths = {
        mount["mountPath"]
        for mount in container.get("volumeMounts", [])
        if mount["name"] in persistent and not mount.get("readOnly", False)
    }
    assert {"/app/config", "/app/prompts", "/app/db"} <= durable_paths
