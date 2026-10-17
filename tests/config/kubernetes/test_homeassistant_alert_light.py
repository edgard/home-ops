import copy

import pytest
import yaml

from tests.support.sources import KubernetesLoader, applications


class HomeAssistantLoader(KubernetesLoader):
    pass


HomeAssistantLoader.add_multi_constructor(
    "!", lambda loader, tag, node: {"tag": tag, "path": loader.construct_scalar(node)}
)


def assert_alert_package(app, gatus):
    config = next(
        d
        for d in app.documents
        if d["metadata"]["name"] == "homeassistant-gatus-alert-light"
    )
    assert "gatus_alert_light.yaml" in config["data"], (
        "Missing native alert-light worker package"
    )
    package = yaml.safe_load(config["data"]["gatus_alert_light.yaml"])
    worker = package["script"]["gatus_alert_light_worker"]
    assert worker["mode"] == "queued" and worker["max"] == 100
    assert worker["variables"]["target_light"] == "light.office_office_mood_light"
    endpoints = worker["variables"]["endpoints"]
    expected = {
        "/".join(filter(None, [e.get("group", ""), e["name"]]))
        for e in gatus.values["config"]["endpoints"]
    }
    assert set(endpoints) == expected
    assert len(set(endpoints.values())) == len(endpoints)
    assert set(endpoints.values()) == {
        "input_boolean." + key for key in package["input_boolean"]
    }
    for helper in [*package["input_boolean"].values(), *package["input_text"].values()]:
        assert "initial" not in helper
    assert package["input_text"]["gatus_alert_light_snapshot"]["max"] == 255
    command = package["rest_command"]["gatus_alert_light_status"]
    assert (
        command["url"] == "http://gatus.platform-system.svc/api/v1/endpoints/statuses"
    )
    assert command["method"] == "GET" and command["timeout"] == 5
    main = next(
        d for d in app.documents if d["metadata"]["name"] == "homeassistant-config"
    )
    inner = yaml.load(main["data"]["configuration.yaml"], Loader=HomeAssistantLoader)
    assert inner["homeassistant"]["packages"] == {
        "tag": "include_dir_named",
        "path": "packages",
    }
    volume = app.values["persistence"]["config-gatus"]
    assert not volume.get("globalMounts")
    assert set(volume["advancedMounts"]["main"]) == {"app"}
    assert {m["path"] for m in volume["advancedMounts"]["main"]["app"]} == {
        "/config/packages/gatus_alert_light.yaml",
        "/config/custom_templates/gatus_alert_light.jinja",
    }
    assert all(m["readOnly"] for m in volume["advancedMounts"]["main"]["app"])


def test_native_alert_package_contract(repo_root):
    apps = {app.name: app for app in applications(repo_root)}
    assert_alert_package(apps["homeassistant"], apps["gatus"])


@pytest.mark.parametrize("broken", ["target", "catalog", "reset", "shared"])
def test_rejects_wrong_target_lost_state_and_shared_package(repo_root, broken):
    apps = {app.name: app for app in applications(repo_root)}
    app = copy.deepcopy(apps["homeassistant"])
    config = next(
        d
        for d in app.documents
        if d["metadata"]["name"] == "homeassistant-gatus-alert-light"
    )
    package = yaml.safe_load(config["data"]["gatus_alert_light.yaml"])
    if broken == "target":
        package["script"]["gatus_alert_light_worker"]["variables"]["target_light"] = (
            "light.unrelated"
        )
    elif broken == "catalog":
        package["script"]["gatus_alert_light_worker"]["variables"][
            "endpoints"
        ].popitem()
    elif broken == "reset":
        package["input_text"]["gatus_alert_light_snapshot"]["initial"] = ""
    else:
        app.values["persistence"]["config-gatus"]["globalMounts"] = [{"path": "/data"}]
    config["data"]["gatus_alert_light.yaml"] = yaml.safe_dump(package)
    with pytest.raises(AssertionError):
        assert_alert_package(app, apps["gatus"])


def test_rendered_alert_package_does_not_change_storage_or_matter(rendered):
    deployment = next(
        d
        for d in rendered
        if d["kind"] == "Deployment"
        and any(
            c["image"].startswith("ghcr.io/home-assistant/home-assistant:")
            for c in d["spec"]["template"]["spec"]["containers"]
        )
    )
    pod = deployment["spec"]["template"]["spec"]
    containers = {c["name"]: c for c in pod["containers"]}
    mounts = containers["app"]["volumeMounts"]
    wanted = {
        "/config/packages/gatus_alert_light.yaml",
        "/config/custom_templates/gatus_alert_light.jinja",
    }
    selected = [m for m in mounts if m["mountPath"] in wanted]
    assert len(selected) == 2 and all(m["readOnly"] for m in selected)
    names = {m["name"] for m in selected}
    assert not names.intersection(
        m["name"] for m in containers["matter-server"]["volumeMounts"]
    )
    assert {
        v["persistentVolumeClaim"]["claimName"]
        for v in pod["volumes"]
        if "persistentVolumeClaim" in v
    } == {"homeassistant", deployment["metadata"]["name"] + "-matter"}


def assert_alert_delivery(gatus):
    config = gatus.values["config"]
    providers = config["alerting"]
    assert {"telegram", "homeassistant"} <= set(providers)
    expected = {
        "failure-threshold": 5,
        "success-threshold": 2,
        "send-on-resolved": True,
    }
    for name in ("telegram", "homeassistant"):
        assert providers[name]["default-alert"] == expected
        assert not providers[name].get("overrides")
    ha = providers["homeassistant"]
    assert ha["url"] == "http://homeassistant.home-automation.svc:8123"
    assert ha["token"] == "$HOMEASSISTANT_GATUS_TOKEN"
    assert not config.get("maintenance")
    for endpoint in config["endpoints"]:
        assert not endpoint.get("maintenance")
        expected_providers = (
            {"homeassistant"}
            if endpoint.get("group") == "acceptance"
            else {"telegram", "homeassistant"}
        )
        assert {a["type"] for a in endpoint["alerts"]} == expected_providers
        assert all(set(a) == {"type"} for a in endpoint["alerts"])
        assert endpoint["interval"] == (
            "5s" if endpoint.get("group") == "acceptance" else "1m"
        )
    secret = next(
        d
        for d in gatus.documents
        if d["kind"] == "ExternalSecret"
        and d["metadata"]["name"] == "gatus-credentials"
    )
    assert {d["secretKey"]: d["remoteRef"]["key"] for d in secret["spec"]["data"]} == {
        "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
        "TELEGRAM_CHAT_ID": "telegram_chat_id",
        "HOMEASSISTANT_GATUS_TOKEN": "homeassistant_gatus_token",
    }
    assert secret["spec"]["secretStoreRef"] == {
        "name": "external-secrets-store",
        "kind": "ClusterSecretStore",
    }
    assert gatus.values["envFrom"] == [{"secretRef": {"name": "gatus-credentials"}}]


def test_gatus_native_provider_and_secret_contract(repo_root):
    gatus = next(app for app in applications(repo_root) if app.name == "gatus")
    assert_alert_delivery(gatus)


@pytest.mark.parametrize(
    "broken",
    ["threshold", "recovery", "telegram", "token", "secret", "maintenance", "override"],
)
def test_rejects_unsafe_or_divergent_alert_delivery(repo_root, broken):
    gatus = copy.deepcopy(
        next(app for app in applications(repo_root) if app.name == "gatus")
    )
    config = gatus.values["config"]
    provider = config["alerting"]["homeassistant"]
    if broken == "threshold":
        provider["default-alert"]["failure-threshold"] = 1
    elif broken == "recovery":
        provider["default-alert"]["send-on-resolved"] = False
    elif broken == "telegram":
        config["endpoints"][0]["alerts"] = [{"type": "homeassistant"}]
    elif broken == "token":
        provider["token"] = "literal-token"
    elif broken == "secret":
        secret = next(d for d in gatus.documents if d["kind"] == "ExternalSecret")
        next(
            d
            for d in secret["spec"]["data"]
            if d["secretKey"] == "HOMEASSISTANT_GATUS_TOKEN"
        )["remoteRef"]["key"] = "wrong_key"
    elif broken == "maintenance":
        config["maintenance"] = [{"start": "00:00", "duration": "1h"}]
    else:
        config["endpoints"][0]["alerts"][0]["failure-threshold"] = 1
    with pytest.raises(AssertionError):
        assert_alert_delivery(gatus)


def test_controlled_acceptance_targets_are_private_and_ephemeral(repo_root):
    gatus = next(app for app in applications(repo_root) if app.name == "gatus")
    endpoints = [
        e for e in gatus.values["config"]["endpoints"] if e.get("group") == "acceptance"
    ]
    assert {e["name"] for e in endpoints} == {"alert-light-a", "alert-light-b"}
    assert {e["url"] for e in endpoints} == {
        "http://gatus-alert-light-acceptance.platform-system.svc:8080/a",
        "http://gatus-alert-light-acceptance.platform-system.svc:8080/b",
    }
    docs = {
        d["kind"]: d
        for d in gatus.documents
        if d["metadata"]["name"] == "gatus-alert-light-acceptance"
    }
    assert set(docs) == {"ConfigMap", "Deployment", "Service"}
    service = docs["Service"]["spec"]
    assert service["type"] == "ClusterIP" and not service.get("externalIPs")
    pod = docs["Deployment"]["spec"]["template"]["spec"]
    assert not pod.get("hostNetwork") and pod["automountServiceAccountToken"] is False
    assert all(
        set(v) - {"name"} in ({"configMap"}, {"emptyDir"}) for v in pod["volumes"]
    )
    assert not any(c.get("envFrom") for c in pod["containers"])
    container = pod["containers"][0]
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 1000
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert container["command"] == ["python", "-B", "/fixture/server.py"]
    script = docs["ConfigMap"]["data"]["server.py"]
    scope = {"__name__": "fixture_test"}
    exec(compile(script, "acceptance-fixture", "exec"), scope)
    from pathlib import Path
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        scope["CONTROL"] = Path(folder)
        assert scope["status"]("/a") == 200
        assert scope["status"]("/b") == 200
        assert scope["status"]("/unknown") == 404
        Path(folder, "fail-a").touch()
        assert scope["status"]("/a") == 503 and scope["status"]("/b") == 200
        assert scope["status"]("/healthz") == 200
