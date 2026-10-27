import json
from math import ceil

from tests.support.sources import read_yaml


def test_native_retrieval_has_generation_embeddings_and_secret_backed_access(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    controllers = values["controllers"]
    main = controllers["main"]["containers"]["app"]["env"]
    gpt = controllers["gpt"]["containers"]["app"]["env"]
    assert main.get("PAPERLESS_AI_ENABLED") == "true"
    assert main.get("PAPERLESS_AI_LLM_BACKEND") == "openai-like"
    assert main.get("PAPERLESS_AI_LLM_MODEL")
    assert main.get("PAPERLESS_AI_LLM_EMBEDDING_BACKEND") == "openai-like"
    assert main.get("PAPERLESS_AI_LLM_EMBEDDING_MODEL")
    assert main.get("PAPERLESS_AI_LLM_API_KEY") == gpt["OPENAI_API_KEY"]
    assert "secretKeyRef" in main["PAPERLESS_AI_LLM_API_KEY"]["valueFrom"]


def test_native_openai_tool_requests_disable_reasoning_and_override_temperature(
    repo_root,
):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["main"]["containers"]["app"]["env"]
    params = json.loads(env.get("PAPERLESS_AI_LLM_EXTRA_PARAMS", "{}"))
    assert params.get("reasoning_effort") == "none"
    assert params.get("temperature") == 1


def test_automatic_enrichment_disables_types_and_preserves_existing_correspondents(
    repo_root,
):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["gpt"]["containers"]["app"]["env"]
    assert env.get("AUTO_GENERATE_DOCUMENT_TYPE") == "false"
    assert env.get("PRESERVE_EXISTING_METADATA") == "true"
    assert env.get("CREATE_NEW_TAGS") == "false"
    assert env.get("AUTO_TAG_COMPLETE") == ""


def test_ocr_preserves_digital_text_and_does_not_replace_original_files(repo_root):
    values = read_yaml(repo_root / "apps/selfhosted/paperless/values.yaml")
    env = values["controllers"]["gpt"]["containers"]["app"]["env"]
    assert env.get("OCR_SKIP_DIGITAL_PAGES") == "true"
    assert env.get("PDF_UPLOAD", "false") == "false"
    assert env.get("PDF_REPLACE", "false") == "false"


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


def test_main_startup_probe_allows_cold_ai_initialization(rendered):
    deployment = next(
        doc
        for doc in rendered
        if doc.get("kind") == "Deployment"
        and any(
            c["image"].startswith("ghcr.io/paperless-ngx/paperless-ngx:")
            for c in doc["spec"]["template"]["spec"]["containers"]
        )
    )
    container = next(
        c
        for c in deployment["spec"]["template"]["spec"]["containers"]
        if c["name"] == "app"
    )
    probe = container["startupProbe"]
    assert probe["failureThreshold"] * probe["periodSeconds"] >= 300
